"""Pre-meeting audio check: confirm loopback + mic are both picking up signal
on whatever device is currently the Windows default. Run this before every
meeting, especially when the playback output changes (e.g. laptop speakers vs
a TV/HDMI display) — the default output device can silently fail to loop back
on some drivers.
"""

import threading

import numpy as np
import soundcard as sc

from .audio import capture_loopback, capture_mic

_SIGNAL_THRESHOLD = 1e-5


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0


def check_audio(duration: float = 5.0) -> bool:
    """Record `duration` seconds from the current default speaker (loopback)
    and default microphone at the same time; print levels. Returns True if
    both channels show signal above the noise floor.
    """
    speaker = sc.default_speaker()
    mic = sc.default_microphone()
    loopback = sc.get_microphone(id=str(speaker.name), include_loopback=True)

    print(f"Default playback device (loopback source): {speaker.name}")
    print(f"Default microphone:                        {mic.name}")
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
            f"  -> Check that '{speaker.name}' is set as the Windows Default Playback\n"
            "     Device (Sound settings), not just Default Communications Device,\n"
            "     and that audio is actually playing through it right now."
        )
    if mic_rms < _SIGNAL_THRESHOLD:
        ok = False
        print(
            "\nWARNING: no mic signal detected.\n"
            f"  -> Check that '{mic.name}' isn't muted and that you spoke during the test."
        )

    if ok:
        print("\nOK — both loopback and mic are capturing signal. Safe to record the meeting.")
    else:
        print("\nFIX THE ABOVE before joining the huddle — a silent channel means that")
        print("side of the conversation won't be in the transcript at all.")
    return ok
