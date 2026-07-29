"""Where each profile's polished summary lands under meetings/.

Layout (raw recordings/transcripts live separately under _raw/<profile>/<date>/):

    meetings/
    ├── sprint/2026-07.md          # one monthly file, appends each sprint
    │                              #   H1: "07/2026 - Sprint 174 & 175"
    ├── client/<ten-khach>/2026-07.md  # per customer, per month (appends)
    └── general/2026-07/<ten>.md   # per month folder, one short-named file each

sprint & client append into a monthly file, so each meeting is written as an
entry delimited by HTML-comment markers and re-running a meeting replaces its
own entry (idempotent) rather than duplicating it. general writes one file
per meeting.
"""

import re
import unicodedata
from pathlib import Path

from .config import MEETINGS_DIR

_ENTRY_RE = re.compile(
    r"<!-- entry:(?P<key>\S+) -->\n(?P<body>.*?)\n<!-- /entry:(?P=key) -->",
    re.DOTALL,
)
_HEADING_RE = re.compile(r"^#{1,5} ")


def _slug(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()


def _shorten(slug: str, max_words: int = 6) -> str:
    return "-".join(slug.split("-")[:max_words])


def _month(meeting_name: str) -> tuple[str, str]:
    """(filename stem 'YYYY-MM', display 'MM/YYYY') from a YYYY-MM-DD name."""
    m = re.match(r"(\d{4})-(\d{2})", meeting_name)
    if m:
        return f"{m.group(1)}-{m.group(2)}", f"{m.group(2)}/{m.group(1)}"
    return meeting_name, meeting_name


def _demote(md: str) -> str:
    """Add one '#' to every heading so a standalone summary (H1 title) can be
    embedded as a section inside a monthly file without clashing with its H1."""
    return "\n".join("#" + ln if _HEADING_RE.match(ln) else ln for ln in md.splitlines())


def _read_entries(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [(m.group("key"), m.group("body")) for m in _ENTRY_RE.finditer(text)]


def _upsert(entries: list[tuple[str, str]], key: str, body: str) -> None:
    for i, (k, _) in enumerate(entries):
        if k == key:
            entries[i] = (key, body)
            return
    entries.append((key, body))


def _write_monthly(path: Path, title: str, entries: list[tuple[str, str]]) -> None:
    blocks = [f"<!-- entry:{k} -->\n{b}\n<!-- /entry:{k} -->" for k, b in entries]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n" + "\n\n".join(blocks).rstrip() + "\n", encoding="utf-8")


def _sprint_num(key: str) -> int | None:
    if key.startswith("sprint-") and key.split("-", 1)[1].isdigit():
        return int(key.split("-", 1)[1])
    return None


def _sprint_title(display: str, entries: list[tuple[str, str]]) -> str:
    nums = sorted({n for n in (_sprint_num(k) for k, _ in entries) if n is not None})
    if nums:
        return f"{display} - Sprint " + " & ".join(str(n) for n in nums)
    return f"{display} - Sprint meetings"


def publish(profile, meeting_name: str, data: dict) -> Path:
    """Render `data` with the profile and write it to its organized location.
    Returns the path of the file written."""
    ym, display = _month(meeting_name)
    rendered = profile.render_summary(meeting_name, data)

    if profile.name == "sprint":
        num = (data.get("sprint_number") or "").strip()
        key = f"sprint-{num}" if num.isdigit() else f"date-{meeting_name}"
        path = MEETINGS_DIR / "sprint" / f"{ym}.md"
        entries = _read_entries(path)
        _upsert(entries, key, _demote(rendered))
        entries.sort(key=lambda kv: (0, _sprint_num(kv[0])) if _sprint_num(kv[0]) is not None else (1, 0))
        _write_monthly(path, _sprint_title(display, entries), entries)
        return path

    if profile.name == "client":
        counterpart = (data.get("counterpart") or "khách").strip()
        path = MEETINGS_DIR / "client" / (_slug(counterpart) or "khach") / f"{ym}.md"
        entries = _read_entries(path)
        _upsert(entries, f"date-{meeting_name}", _demote(rendered))
        _write_monthly(path, f"{counterpart} — {display}", entries)
        return path

    # general (and any future per-meeting profile): one short-named file/month
    name = _shorten(_slug(data.get("meeting_title") or "")) or _slug(meeting_name) or "hop"
    path = MEETINGS_DIR / profile.name / ym / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return path
