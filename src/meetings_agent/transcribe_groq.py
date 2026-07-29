"""Transcribe the meeting recording using Groq's hosted Whisper API (cloud).

Far faster than local CPU transcription (large-v3 quality, ~50-100x realtime),
at the cost of uploading the recording to Groq's servers. Chunks the WAV into
pieces under Groq's free-tier 25MB upload limit and stitches per-chunk
segments back into a single timeline, so output matches transcribe.py's
transcript.md/segments.json format exactly.
"""

import io
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import GROQ_API_KEY, GROQ_MODEL, WHISPER_LANGUAGE
from .transcribe import _load_whisper_keywords, _timestamp

CHUNK_SECONDS = 600  # ~19.2MB at 16kHz/mono/16-bit — safely under the 25MB free-tier limit
SPLIT_SEARCH_SECONDS = 20  # how far around the nominal boundary to look for a quiet spot
SPLIT_RMS_WINDOW = 1.0  # seconds of audio scored per candidate split point


def _split_points(data: np.ndarray, sr: int) -> list[int]:
    """Chunk boundaries at the quietest moment near each nominal boundary.

    A hard cut every CHUNK_SECONDS routinely lands mid-word, and whisper
    then misrecognizes (or drops) the word on both sides of the cut. Instead,
    scan ±SPLIT_SEARCH_SECONDS around each nominal boundary and cut at the
    centre of the quietest RMS window — almost always a pause between
    sentences or speakers.
    """
    points = [0]
    win = int(SPLIT_RMS_WINDOW * sr)
    search = SPLIT_SEARCH_SECONDS * sr
    stride = sr // 4
    pos = CHUNK_SECONDS * sr
    while pos < len(data):
        lo = max(points[-1] + win, pos - search)
        hi = min(len(data) - win, pos + search)
        best, best_rms = pos, None
        for start in range(lo, hi, stride):
            seg = data[start : start + win].astype(np.float32)
            rms = float(np.sqrt(np.mean(seg * seg)))
            if best_rms is None or rms < best_rms:
                best_rms, best = rms, start + win // 2
        points.append(best)
        pos = best + CHUNK_SECONDS * sr
    points.append(len(data))
    return points


def transcribe_groq(meeting_dir: Path) -> Path:
    """Transcribe recording.wav via Groq into transcript.md + segments.json."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set in .env")

    from groq import Groq  # slow import — keep it lazy

    wav_path = meeting_dir / "recording.wav"
    if not wav_path.exists():
        raise FileNotFoundError(f"{wav_path} not found — run `meetings-agent record` first.")

    client = Groq(api_key=GROQ_API_KEY)
    prompt = _load_whisper_keywords()
    if prompt:
        print(f"Priming Groq with glossary keywords: {prompt}")

    data, sr = sf.read(str(wav_path), dtype="int16")
    points = _split_points(data, sr)
    n_chunks = len(points) - 1

    print(f"Transcribing {wav_path} via Groq ({GROQ_MODEL}), {n_chunks} chunk(s), "
          "split at quiet points...")

    records = []
    for i in range(n_chunks):
        start, end = points[i], points[i + 1]

        buf = io.BytesIO()
        sf.write(buf, data[start:end], sr, format="WAV", subtype="PCM_16")

        print(f"  chunk {i + 1}/{n_chunks} ({start / sr:.0f}s-{end / sr:.0f}s)...")
        resp = client.audio.transcriptions.create(
            file=(f"chunk_{i}.wav", buf.getvalue()),
            model=GROQ_MODEL,
            language=WHISPER_LANGUAGE or "vi",
            prompt=prompt,
            response_format="verbose_json",
        )

        offset = start / sr
        for seg in resp.segments or []:
            text = (seg["text"] if isinstance(seg, dict) else seg.text).strip()
            if not text:
                continue
            seg_start = seg["start"] if isinstance(seg, dict) else seg.start
            ts = _timestamp(offset + seg_start)
            records.append({"timestamp": ts, "text": text})
            print(f"[{ts}] {text}")

    lines = [f"# Transcript — {meeting_dir.name}", "", f"Ngôn ngữ: {WHISPER_LANGUAGE or 'vi'}", ""]
    lines += [f"[{r['timestamp']}] {r['text']}" for r in records]

    transcript_path = meeting_dir / "transcript.md"
    transcript_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    segments_path = meeting_dir / "segments.json"
    segments_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nSaved transcript to {transcript_path}")
    print(f"Saved segments to {segments_path} (used by `meetings-agent correct`)")
    return transcript_path
