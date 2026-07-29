"""Transcribe the meeting recording with faster-whisper (runs locally).

Primes whisper with your team's vocabulary from glossary.md (the
"Whisper prompt keywords" line) so jargon and product names are more likely
to be heard correctly in the first pass. Also writes segments.json so the
`correct` step can run a second, context-aware pass with Claude afterward.
"""

import json
from pathlib import Path

from .config import GLOSSARY_FILE, WHISPER_LANGUAGE, WHISPER_MODEL


def _timestamp(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _load_whisper_keywords() -> str | None:
    if not GLOSSARY_FILE.exists():
        return None
    text = GLOSSARY_FILE.read_text(encoding="utf-8")
    marker = "## Whisper prompt keywords"
    if marker not in text:
        return None
    for line in text.split(marker, 1)[1].splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---"):
            return line
    return None


def transcribe(meeting_dir: Path) -> Path:
    """Transcribe recording.wav into transcript.md + segments.json."""
    from faster_whisper import WhisperModel  # slow import — keep it lazy

    wav_path = meeting_dir / "recording.wav"
    if not wav_path.exists():
        raise FileNotFoundError(f"{wav_path} not found — run `meetings-agent record` first.")

    print(f"Loading whisper model '{WHISPER_MODEL}'...")
    model = WhisperModel(WHISPER_MODEL, device="auto", compute_type="auto")

    initial_prompt = _load_whisper_keywords()
    if initial_prompt:
        print(f"Priming whisper with glossary keywords: {initial_prompt}")

    print(f"Transcribing {wav_path} (this can take a while)...")
    segments, info = model.transcribe(
        str(wav_path),
        language=WHISPER_LANGUAGE,
        vad_filter=True,
        initial_prompt=initial_prompt,
    )

    lines = [f"# Transcript — {meeting_dir.name}", "", f"Ngôn ngữ: {info.language}", ""]
    records = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            ts = _timestamp(seg.start)
            lines.append(f"[{ts}] {text}")
            records.append({"timestamp": ts, "text": text})
            print(f"[{ts}] {text}")

    transcript_path = meeting_dir / "transcript.md"
    transcript_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    segments_path = meeting_dir / "segments.json"
    segments_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nSaved transcript to {transcript_path}")
    print(f"Saved segments to {segments_path} (used by `meetings-agent correct`)")
    return transcript_path
