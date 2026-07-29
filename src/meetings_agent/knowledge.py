"""Append a meeting's knowledge updates to the shared knowledge file."""

from pathlib import Path


def sync(meeting_dir: Path, knowledge_file: Path) -> None:
    snippet_path = meeting_dir / "knowledge.md"
    if not snippet_path.exists():
        raise FileNotFoundError(f"{snippet_path} not found — run `meetings-agent summarize` first.")

    snippet = snippet_path.read_text(encoding="utf-8")
    marker = snippet.splitlines()[0].strip()

    knowledge_file.parent.mkdir(parents=True, exist_ok=True)
    existing = knowledge_file.read_text(encoding="utf-8") if knowledge_file.exists() else ""

    if marker and marker in existing:
        print(f"'{marker}' already present in {knowledge_file} — skipping (edit manually to re-sync).")
        return

    with knowledge_file.open("a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write("\n" + snippet)

    print(f"Appended knowledge updates to {knowledge_file}")
