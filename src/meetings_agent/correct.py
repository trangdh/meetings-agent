"""Fix ASR mis-recognitions in the raw transcript using Claude + your team's
glossary. faster-whisper has no idea about your team's internal product
names, feature names, or abbreviations, so it frequently mishears them —
this pass re-reads every line with full conversation context plus the
glossary to correct likely misrecognitions, without changing meaning,
translating, or summarizing.

Cost/robustness design:
- Diff output: the model returns only the lines it CHANGES ({index, text}),
  not the whole transcript. Output tokens (the expensive half) drop ~80% on
  a typical meeting where most lines are already correct, and the earlier
  "returned N-1 lines" alignment bug is gone — unchanged lines pass through
  verbatim, and we validate indices are in range instead of counting lines.
- Batching keeps index references short and reliable on long meetings; each
  batch sees the tail of the previous (already-corrected) batch as read-only
  context for continuity across the boundary.
- Prompt caching: the system instructions + glossary are identical across
  all batches, so they're marked cache_control and re-read at ~0.1x cost.
- Thinking is disabled — this is mechanical find-and-fix, not reasoning.
"""

import json
from pathlib import Path

import anthropic

from .config import CLAUDE_MODEL, CORRECTION_PROMPT_FILE, GLOSSARY_FILE, anthropic_client

EDITS_SCHEMA = {
    "type": "object",
    "properties": {
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["index", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["edits"],
    "additionalProperties": False,
}

BATCH_SIZE = 200
CONTEXT_TAIL = 10
CONTEXT_LOOKAHEAD = 10
MAX_RETRIES = 2


def _correct_batch(client: anthropic.Anthropic, system_blocks: list, batch: list[dict],
                   context_lines: list[str], lookahead_lines: list[str]) -> list[str]:
    """Return the batch's lines with any model-suggested edits applied by index."""
    numbered = "\n".join(f"{i}. {s['text']}" for i, s in enumerate(batch))
    parts = []
    if context_lines:
        parts.append("## Ngữ cảnh liền trước (đã sửa, KHÔNG sửa lại, chỉ để tham khảo)\n\n"
                     + "\n".join(context_lines))
    parts.append(f"## Đoạn cần soát ({len(batch)} dòng, đánh số từ 0)\n\n{numbered}")
    if lookahead_lines:
        # Corrections near the end of a batch often hinge on what's said
        # next (a term is introduced mid-sentence and clarified a line later),
        # so show the raw start of the following batch as read-only context.
        parts.append("## Ngữ cảnh liền sau (CHƯA sửa, KHÔNG đưa vào edits, chỉ để tham khảo)\n\n"
                     + "\n".join(lookahead_lines))
    user_content = "\n\n".join(parts)

    result = [s["text"] for s in batch]
    for attempt in range(1, MAX_RETRIES + 1):
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8_000,
            thinking={"type": "disabled"},
            system=system_blocks,
            output_config={"format": {"type": "json_schema", "schema": EDITS_SCHEMA}},
            messages=[{"role": "user", "content": user_content}],
        )
        if response.stop_reason == "max_tokens":
            print(f"    attempt {attempt}: truncated (max_tokens), retrying...")
            continue

        text = next(b.text for b in response.content if b.type == "text")
        edits = json.loads(text)["edits"]

        out_of_range = [e["index"] for e in edits if not (0 <= e["index"] < len(batch))]
        if out_of_range:
            print(f"    attempt {attempt}: {len(out_of_range)} edit(s) with out-of-range index"
                  + (", retrying..." if attempt < MAX_RETRIES else " — ignoring those edits."))
            if attempt < MAX_RETRIES:
                continue

        for e in edits:
            if 0 <= e["index"] < len(batch):
                result[e["index"]] = e["text"]
        return result

    print(f"    giving up after {MAX_RETRIES} attempts — keeping original text for this batch.")
    return [s["text"] for s in batch]


def correct(meeting_dir: Path) -> Path:
    """Correct transcript.md using segments.json + glossary.md -> transcript_corrected.md."""
    segments_path = meeting_dir / "segments.json"
    if not segments_path.exists():
        raise FileNotFoundError(f"{segments_path} not found — run `meetings-agent transcribe` first.")

    segments = json.loads(segments_path.read_text(encoding="utf-8"))
    if not segments:
        raise RuntimeError("Transcript has no segments to correct.")

    glossary = (
        GLOSSARY_FILE.read_text(encoding="utf-8")
        if GLOSSARY_FILE.exists()
        else "(Chưa có glossary — sửa dựa trên ngữ cảnh chung.)"
    )
    system_prompt = CORRECTION_PROMPT_FILE.read_text(encoding="utf-8")
    # Stable across every batch -> cache it so batches 2..N read it at ~0.1x cost.
    system_blocks = [
        {"type": "text", "text": system_prompt},
        {
            "type": "text",
            "text": f"## Glossary thuật ngữ\n\n{glossary}",
            "cache_control": {"type": "ephemeral"},
        },
    ]
    client = anthropic_client()

    batches = [segments[i : i + BATCH_SIZE] for i in range(0, len(segments), BATCH_SIZE)]
    print(f"Correcting transcript with {CLAUDE_MODEL} using your glossary "
          f"({len(segments)} lines, {len(batches)} batch(es))...")

    all_corrected: list[str] = []
    for i, batch in enumerate(batches, start=1):
        print(f"  batch {i}/{len(batches)} ({len(batch)} lines)...")
        context_lines = all_corrected[-CONTEXT_TAIL:] if all_corrected else []
        lookahead = [s["text"] for s in batches[i][:CONTEXT_LOOKAHEAD]] if i < len(batches) else []
        all_corrected.extend(_correct_batch(client, system_blocks, batch, context_lines, lookahead))

    changed = sum(
        1 for orig, new in zip(segments, all_corrected) if orig["text"].strip() != new.strip()
    )

    out_lines = [f"# Transcript (corrected) — {meeting_dir.name}", ""]
    for seg, new_text in zip(segments, all_corrected):
        out_lines.append(f"[{seg['timestamp']}] {new_text.strip()}")

    out_path = meeting_dir / "transcript_corrected.md"
    out_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"Corrected {changed}/{len(segments)} line(s). Saved {out_path}")
    return out_path
