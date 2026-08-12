"""Pre-meeting audio check: confirm loopback + mic are both picking up signal.
Run this before every meeting, especially when the playback output changes
(e.g. laptop speakers vs a TV/HDMI display, or a newly-set-up virtual audio
device on macOS/Linux) — the loopback source can silently fail on some setups.
"""

import threading

import numpy as np
import soundcard as sc

from .audio import MACOS_SILENCE_HINT, capture_loopback, capture_mic, loopback_source

_SIGNAL_THRESHOLD = 1e-5


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0


def check_audio(duration: float = 5.0) -> bool:
    """Record `duration` seconds from the loopback source and default
    microphone at the same time; print levels. Returns True if both channels
    show signal above the noise floor.
    """
    loopback_label, loopback = loopback_source()
    mic = sc.default_microphone()

    print(f"Loopback source (system audio): {loopback_label}")
    print(f"Default microphone:             {mic.name}")
    print(f"\nRecording {duration:.0f}s — play audio through the meeting's output device")
    print("and say a few words into the mic now...")

    stop = threading.Event()
    loop_chunks: list = []
    mic_chunks: list = []
    t1 = threading.Thread(target=capture_loopback, args=(loopback, stop, loop_chunks))
    t2 = threading.Thread(target=capture_mic, args=(mic, stop, mic_chunks))
    t1.start()
    t2.start()
    threading.Timer(duration, stop.set).start()
    t1.join()
    t2.join()

    loop_audio = np.concatenate(loop_chunks) if loop_chunks else np.zeros(0)
    mic_audio = np.concatenate(mic_chunks) if mic_chunks else np.zeros(0)
    loop_rms = _rms(loop_audio)
    mic_rms = _rms(mic_audio)

    print(f"\nLoopback RMS: {loop_rms:.6f}")
    print(f"Mic RMS:      {mic_rms:.6f}")

    ok = True
    if loop_rms < _SIGNAL_THRESHOLD:
        ok = False
        print(
            "\nWARNING: no loopback signal detected.\n"
            f"  -> Check that '{loopback_label}' is actually receiving system audio right now:\n"
            "     on Windows, it must be the Default Playback Device (Sound settings), not\n"
            "     just Default Communications Device; on macOS/Linux, check that your\n"
            "     Multi-Output Device / virtual audio device is the current output and that\n"
            "     LOOPBACK_DEVICE in .env matches it."
            + MACOS_SILENCE_HINT
        )
    if mic_rms < _SIGNAL_THRESHOLD:
        ok = False
        print(
            "\nWARNING: no mic signal detected.\n"
            f"  -> Check that '{mic.name}' isn't muted and that you spoke during the test."
            + MACOS_SILENCE_HINT
        )

    if ok:
        print("\nOK — both loopback and mic are capturing signal. Safe to record the meeting.")
    else:
        print("\nFIX THE ABOVE before joining the huddle — a silent channel means that")
        print("side of the conversation won't be in the transcript at all.")
    return ok
