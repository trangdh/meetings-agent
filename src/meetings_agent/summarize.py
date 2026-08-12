"""Summarize a meeting transcript with Claude into structured notes.

The output structure depends on the meeting profile (sprint, general, ...);
see profiles.py. Everything else in the pipeline is profile-agnostic.
"""

import json
from pathlib import Path

from .config import AUTO_PUSH, CLAUDE_MODEL, GLOSSARY_FILE, MEETING_TYPE, anthropic_client
from .output_layout import publish
from .profiles import get_profile


def summarize(meeting_dir: Path, meeting_type: str | None = None,
              sprint_number: str | None = None) -> Path:
    """Summarize transcript_corrected.md (if present) or transcript.md.

    Writes machine records (summary.json, knowledge.md) into the raw meeting
    folder, then publishes the human-readable summary into its profile-organized
    location under meetings/ (see output_layout.py). Returns the path
    of the published summary."""
    requested = meeting_type or MEETING_TYPE

    corrected_path = meeting_dir / "transcript_corrected.md"
    transcript_path = corrected_path if corrected_path.exists() else meeting_dir / "transcript.md"
    if not transcript_path.exists():
        raise FileNotFoundError(f"{transcript_path} not found — run `meetings-agent transcribe` first.")
    print(f"Using {transcript_path.name} as the source transcript.")
    transcript = transcript_path.read_text(encoding="utf-8")

    # "auto": detect the type from the transcript so a meeting recorded without
    # switching the profile still lands in the right place (not merged into sprint).
    if requested == "auto":
        from .classify import detect_profile
        detected, reason = detect_profile(transcript)
        print(f"Auto-detected meeting type: {detected} — {reason}")
        requested = detected

    profile = get_profile(requested)
    print(f"Meeting profile: {profile.name} ({profile.label})")

    system_blocks = [{"type": "text", "text": profile.prompt_file.read_text(encoding="utf-8")}]
    if GLOSSARY_FILE.exists():
        system_blocks.append({
            "type": "text",
            "text": (
                "## Glossary thuật ngữ — CHÍNH TẢ THAM CHIẾU\n\n"
                "Khi nhắc đến bất kỳ thuật ngữ/tên riêng nào dưới đây trong bản tóm tắt, "
                "phải chép ĐÚNG NGUYÊN VĂN cách viết ở đây, không tự sửa hay chuẩn hóa lại:\n\n"
                + GLOSSARY_FILE.read_text(encoding="utf-8")
            ),
        })

    client = anthropic_client()
    print(f"Summarizing with {CLAUDE_MODEL}...")
    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=32_000,
        thinking={"type": "adaptive"},
        system=system_blocks,
        output_config={"format": {"type": "json_schema", "schema": profile.schema}},
        messages=[{
            "role": "user",
            "content": f"Transcript {profile.label.lower()} ({meeting_dir.name}):\n\n{transcript}",
        }],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "max_tokens":
        raise RuntimeError("Summary was truncated (max_tokens) — transcript may be too long.")

    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    # --sprint (or an env/GUI value) overrides the number extracted from the
    # transcript — used to name the sprint monthly file (active sprint + 1).
    if sprint_number:
        data["sprint_number"] = str(sprint_number).strip()

    # Record token usage so cost can be computed later without guessing from
    # file sizes — response.usage is otherwise discarded after this call.
    usage = response.usage
    data["_usage"] = {
        "model": CLAUDE_MODEL,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_creation_input_tokens": usage.cache_creation_input_tokens,
        "cache_read_input_tokens": usage.cache_read_input_tokens,
    }

    # Machine records stay in the raw folder for provenance + `sync`.
    (meeting_dir / "summary.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (meeting_dir / "knowledge.md").write_text(
        profile.render_knowledge(meeting_dir.name, data), encoding="utf-8"
    )

    # The polished, human-readable summary goes to its profile-organized home.
    published = publish(profile, meeting_dir.name, data)

    print(f"Published summary -> {published}")
    print(f"Raw records in {meeting_dir} ({len(data['knowledge_updates'])} knowledge updates)")

    if AUTO_PUSH:
        from .git_push import auto_push
        auto_push([published], f"Meeting summary: {profile.name} {meeting_dir.name}")

    return published
