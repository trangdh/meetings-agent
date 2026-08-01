"""Record the huddle: system audio (loopback) mixed with the local microphone.

Loopback captures everyone speaking in the huddle (what comes out of the
speakers); the microphone captures the person running the agent.
"""

import sys
import threading
import time
from pathlib import Path

import numpy as np
import soundcard as sc
import soundfile as sf

from .config import LOOPBACK_DEVICE, SAMPLE_RATE


def loopback_source():
    """Return (label, soundcard device) for the loopback/system-audio source.

    Windows has real WASAPI loopback (`include_loopback=True`), so the
    current default speaker works out of the box with no setup. macOS and
    Linux have no such API — `soundcard` can only record from *input*
    devices there, so system audio has to be routed to a virtual audio
    device first (e.g. BlackHole on macOS, a PulseAudio monitor source on
    Linux) and picked up like a regular microphone. `LOOPBACK_DEVICE` in
    `.env` names that device (see README, mục "Setup audio trên macOS").
    """
    if LOOPBACK_DEVICE:
        return LOOPBACK_DEVICE, sc.get_microphone(LOOPBACK_DEVICE)
    if sys.platform == "win32":
        speaker = sc.default_speaker()
        return speaker.name, sc.get_microphone(id=str(speaker.name), include_loopback=True)
    raise RuntimeError(
        "Không có API loopback mặc định trên hệ điều hành này (chỉ Windows có WASAPI "
        "loopback tự động). Cài virtual audio device (vd BlackHole trên macOS) rồi đặt "
        "LOOPBACK_DEVICE trong .env — xem README mục 'Setup audio trên macOS'."
    )

# 4096 samples = 256ms per read at 16kHz. Larger blocks mean fewer Python
# wakeups per second, which matters because a busy machine (screen share,
# many tabs) can starve the capture threads — if a read is late, WASAPI's
# ring buffer overflows and samples are dropped *silently*. Observed as
# intermittent missing audio on real meetings with the old 64ms blocks.
_BLOCK = 4096
_LOOPBACK_PROBE_ATTEMPTS = 3
_PROBE_FRAMES = SAMPLE_RATE // 4  # ~0.25s dead-stream probe, independent of _BLOCK
_RECONNECT_BACKOFF = 2  # seconds to wait before reopening a stream that errored
_GAP_PAD_THRESHOLD = SAMPLE_RATE // 10  # pad reconnect gaps longer than 100ms


def _pad_gap(chunks: list, written: int, started_at: float, label: str) -> int:
    """Insert silence covering audio lost while a stream was down MID-SESSION.

    The two capture channels are mixed by sample index, not wall-clock time,
    so an un-padded reconnect gap doesn't just lose that audio — it shifts the
    channel earlier and desyncs it against the other channel for the rest of
    the meeting. Only called on a RE-open (never the first open), so it never
    fabricates leading silence for the stream's initial open latency.
    """
    expected = int((time.monotonic() - started_at) * SAMPLE_RATE)
    deficit = expected - written
    if deficit > _GAP_PAD_THRESHOLD:
        chunks.append(np.zeros(deficit, dtype=np.float32))
        print(f"  [{label}] padded {deficit / SAMPLE_RATE:.1f}s of downtime with silence "
              "to keep channels aligned")
        return written + deficit
    return written


def is_dead_silence(data: np.ndarray) -> bool:
    """True if `data` is bit-exact zero.

    A live WASAPI loopback stream carries a noise floor even during real
    silence (mixer/APO artifacts), so bit-exact zero across an entire probe
    window means the *stream* came up dead, not that nothing is playing.
    Observed intermittently — reproducibly, roughly every other attempt in
    testing — on both a laptop's integrated audio and an HDMI/TV display
    audio output: the loopback capture silently returns zeros for its whole
    duration, and simply reopening the stream fixes it.
    """
    return not np.any(data)


def capture_mic(device, stop: threading.Event, chunks: list,
                pause: threading.Event | None = None) -> None:
    """Capture the microphone, reopening the stream if it errors mid-session
    (e.g. AUDCLNT_E_DEVICE_INVALIDATED — observed after ~100 minutes on a
    real meeting, likely tied to a display/power-state change invalidating
    the audio endpoint) instead of letting the capture thread die silently.

    When `pause` is set, audio is dropped (not silence-padded) so pause/resume
    skips that span entirely; both channels share the same pause Event so they
    stay aligned.
    """
    started_at = None
    written = 0
    pause_started = None
    while not stop.is_set():
        try:
            with device.recorder(samplerate=SAMPLE_RATE, blocksize=_BLOCK) as rec:
                if started_at is None:
                    # Start the alignment clock at the first captured frame, so
                    # the stream's open latency isn't mistaken for a dropout and
                    # padded with leading silence (that used to push the start of
                    # the meeting back by a second-plus and read as "lost audio").
                    started_at = time.monotonic()
                else:
                    written = _pad_gap(chunks, written, started_at, "mic")
                while not stop.is_set():
                    data = rec.record(numframes=_BLOCK)
                    # While paused, keep draining the stream but drop the audio;
                    # on resume, shift the clock past the pause so the skipped
                    # span isn't later mistaken for a dropout and padded.
                    if pause is not None and pause.is_set():
                        if pause_started is None:
                            pause_started = time.monotonic()
                        continue
                    if pause_started is not None:
                        started_at += time.monotonic() - pause_started
                        pause_started = None
                    chunks.append(data.mean(axis=1))  # downmix to mono
                    written += len(data)
        except Exception as e:
            if stop.is_set():
                return
            print(f"  [mic] stream error ({e!r}), reconnecting in {_RECONNECT_BACKOFF}s...")
            stop.wait(_RECONNECT_BACKOFF)


def capture_loopback(device, stop: threading.Event, chunks: list,
                     pause: threading.Event | None = None) -> None:
    """Capture the loopback source. Reopens the stream if it comes up
    dead-silent on open (a startup quirk) or errors mid-session (e.g. the
    device being invalidated) instead of letting the capture thread die.

    Honors `pause` the same way as capture_mic (drops audio while paused).
    """
    started_at = None
    written = 0
    silent_attempts = 0
    pause_started = None
    while not stop.is_set():
        try:
            with device.recorder(samplerate=SAMPLE_RATE, blocksize=_BLOCK) as rec:
                # Short probe (~0.25s) to catch the dead-on-open quirk cheaply.
                probe = rec.record(numframes=_PROBE_FRAMES)
                if is_dead_silence(probe) and silent_attempts < _LOOPBACK_PROBE_ATTEMPTS - 1:
                    silent_attempts += 1
                    print(f"  [loopback] stream came up silent (attempt {silent_attempts}/{_LOOPBACK_PROBE_ATTEMPTS}), reopening...")
                    continue
                if is_dead_silence(probe):
                    print(
                        f"  [loopback] WARNING: still silent after {_LOOPBACK_PROBE_ATTEMPTS} attempts — "
                        "system audio may not be captured for this meeting. "
                        "Run `meetings-agent check-audio` to investigate."
                    )
                silent_attempts = 0
                if started_at is None:
                    # Clock starts at the first accepted frame (see capture_mic):
                    # no leading silence for open latency; pad only real
                    # mid-session reconnect gaps.
                    started_at = time.monotonic()
                else:
                    written = _pad_gap(chunks, written, started_at, "loopback")
                chunks.append(probe.mean(axis=1))
                written += len(probe)
                while not stop.is_set():
                    data = rec.record(numframes=_BLOCK)
                    if pause is not None and pause.is_set():
                        if pause_started is None:
                            pause_started = time.monotonic()
                        continue
                    if pause_started is not None:
                        started_at += time.monotonic() - pause_started
                        pause_started = None
                    chunks.append(data.mean(axis=1))
                    written += len(data)
        except Exception as e:
            if stop.is_set():
                return
            print(f"  [loopback] stream error ({e!r}), reconnecting in {_RECONNECT_BACKOFF}s...")
            stop.wait(_RECONNECT_BACKOFF)


def record(meeting_dir: Path) -> Path:
    """Record until Ctrl+C, or until a `.stop` file appears in meeting_dir
    (lets a supervising process — e.g. an orchestrating script — stop the
    recording gracefully without sending a signal Python can't intercept).
    Returns the path of the mixed WAV file."""
    meeting_dir.mkdir(parents=True, exist_ok=True)
    wav_path = meeting_dir / "recording.wav"
    stop_file = meeting_dir / ".stop"
    pause_file = meeting_dir / ".pause"
    stop_file.unlink(missing_ok=True)  # clear stale signals from a previous run
    pause_file.unlink(missing_ok=True)

    loopback_label, loopback = loopback_source()
    mic = sc.default_microphone()

    print(f"Recording huddle audio -> {wav_path}")
    print(f"  loopback: {loopback_label}")
    print(f"  mic:      {mic.name}")
    print(f"Press Ctrl+C to stop, or create {stop_file} to stop remotely.")

    stop = threading.Event()
    pause = threading.Event()
    loop_chunks: list = []
    mic_chunks: list = []
    threads = [
        threading.Thread(target=capture_loopback, args=(loopback, stop, loop_chunks, pause), daemon=True, name="loopback"),
        threading.Thread(target=capture_mic, args=(mic, stop, mic_chunks, pause), daemon=True, name="mic"),
    ]
    for t in threads:
        t.start()

    warned_dead: set[str] = set()
    try:
        while not stop_file.exists():
            stop.wait(1)
            # Pause/resume driven by a `.pause` sentinel (mirrors `.stop`), so a
            # supervising process (the GUI) can toggle it without a signal.
            if pause_file.exists() and not pause.is_set():
                pause.set()
                print("  [record] paused")
            elif not pause_file.exists() and pause.is_set():
                pause.clear()
                print("  [record] resumed")
            # Belt-and-suspenders: capture_* now retries on its own errors and
            # should never exit before `stop` is set, but if something truly
            # unexpected escapes it, surface that loudly instead of silently
            # saving a truncated recording with no warning.
            for t in threads:
                if not t.is_alive() and t.name not in warned_dead:
                    print(f"  WARNING: '{t.name}' capture thread stopped unexpectedly — "
                          "that audio channel may be missing from this point on.")
                    warned_dead.add(t.name)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        stop_file.unlink(missing_ok=True)
        pause_file.unlink(missing_ok=True)
        for t in threads:
            t.join(timeout=5)

    loop_audio = np.concatenate(loop_chunks) if loop_chunks else np.zeros(0)
    mic_audio = np.concatenate(mic_chunks) if mic_chunks else np.zeros(0)
    length = max(len(loop_audio), len(mic_audio))
    if length == 0:
        raise RuntimeError("No audio captured.")

    mixed = np.zeros(length, dtype=np.float32)
    mixed[: len(loop_audio)] += loop_audio
    mixed[: len(mic_audio)] += mic_audio
    peak = np.abs(mixed).max()
    if peak > 1.0:
        mixed /= peak

    sf.write(wav_path, mixed, SAMPLE_RATE)
    print(f"\nSaved {length / SAMPLE_RATE / 60:.1f} minutes of audio to {wav_path}")
    return wav_path
