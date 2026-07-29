"""Meeting profiles: each one describes how to summarize a different kind of
meeting (prompt + output schema + how to render the result).

Only the `summarize` step is meeting-type specific — record, transcribe,
correct, and sync are shared across every profile. Add a new meeting type by
adding a Profile here (and its prompt file under prompts/); nothing in the
core pipeline changes.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import CLIENT_PROMPT_FILE, GENERAL_PROMPT_FILE, SPRINT_PROMPT_FILE


@dataclass(frozen=True)
class Profile:
    name: str
    label: str  # human name used in prompts/titles, e.g. "sprint meeting"
    prompt_file: Path
    schema: dict
    render_summary: Callable[[str, dict], str]
    render_knowledge: Callable[[str, dict], str]


# --------------------------------------------------------------------------
# Shared: knowledge_updates has the same shape (topic/content) in every
# profile, so its rendering is shared.
# --------------------------------------------------------------------------
def _render_knowledge(label: str, meeting_name: str, updates: list[dict]) -> str:
    lines = [f"## {label} {meeting_name}", ""]
    if not updates:
        lines.append("_Không có knowledge update nào từ buổi họp này._")
    for k in updates:
        lines += [f"### {k['topic']}", "", k["content"], ""]
    return "\n".join(lines) + "\n"


# ==========================================================================
# Sprint profile — the original 4-part sprint meeting structure.
# ==========================================================================
SPRINT_SCHEMA = {
    "type": "object",
    "properties": {
        "meeting_title": {"type": "string"},
        "sprint_number": {"type": "string"},
        "sprint_goal_review": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["achieved", "partial", "not_achieved", "unclear"]},
                "summary": {"type": "string"},
                "major_updates": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["status", "summary", "major_updates"],
            "additionalProperties": False,
        },
        "roadmap": {
            "type": "object",
            "properties": {
                "completed_epics": {"type": "array", "items": {"type": "string"}},
                "next_epics": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string"},
            },
            "required": ["completed_epics", "next_epics", "notes"],
            "additionalProperties": False,
        },
        # --- Part B: dev + QA planning breakout ---
        "next_sprint_goal": {"type": "string"},
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": "string"},
                    "due": {"type": "string"},
                },
                "required": ["task", "owner", "due"],
                "additionalProperties": False,
            },
        },
        "knowledge_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["topic", "content"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "meeting_title", "sprint_number", "sprint_goal_review", "roadmap",
        "next_sprint_goal", "action_items", "knowledge_updates",
    ],
    "additionalProperties": False,
}

def sprint_title(meeting_name: str, d: dict) -> str:
    """H1 title for a standalone sprint summary."""
    num = (d.get("sprint_number") or "").strip()
    base = f"Sprint {num}" if num else (d.get("meeting_title") or "Sprint meeting")
    return f"{base} — {meeting_name}"


def _render_sprint_summary(meeting_name: str, d: dict) -> str:
    goal = d["sprint_goal_review"]
    roadmap = d["roadmap"]
    lines = [
        f"# {sprint_title(meeting_name, d)}",
        "",
        "## 1. Tổng kết sprint vừa rồi",
        f"**Kết quả:** {goal['status']}",
        "",
        goal["summary"],
    ]
    if goal["major_updates"]:
        lines += ["", "**Update lớn:**"] + [f"- {u}" for u in goal["major_updates"]]

    lines += ["", "## 2. Roadmap sprint tới"]
    if roadmap["completed_epics"]:
        lines += ["**Epic đã hoàn thành:**"] + [f"- {e}" for e in roadmap["completed_epics"]]
    if roadmap["next_epics"]:
        lines += ["", "**Epic sprint tới:**"] + [f"- {e}" for e in roadmap["next_epics"]]
    if roadmap["notes"]:
        lines += ["", roadmap["notes"]]
    if d.get("next_sprint_goal"):
        lines += ["", f"**Sprint goal:** {d['next_sprint_goal']}"]

    lines += ["", "## Next actions"]
    for item in d["action_items"]:
        due = f" (deadline: {item['due']})" if item["due"] else ""
        owner = f" — **{item['owner']}**" if item["owner"] else ""
        lines.append(f"- [ ] {item['task']}{owner}{due}")

    return "\n".join(lines) + "\n"


# ==========================================================================
# General profile — flexible, works for any meeting that isn't a sprint.
# ==========================================================================
GENERAL_SCHEMA = {
    "type": "object",
    "properties": {
        "meeting_title": {"type": "string"},
        "overview": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "points": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["heading", "points"],
                "additionalProperties": False,
            },
        },
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "decision": {"type": "string"},
                    "context": {"type": "string"},
                },
                "required": ["decision", "context"],
                "additionalProperties": False,
            },
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": "string"},
                    "due": {"type": "string"},
                },
                "required": ["task", "owner", "due"],
                "additionalProperties": False,
            },
        },
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "knowledge_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["topic", "content"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "meeting_title", "overview", "sections", "decisions",
        "action_items", "open_questions", "knowledge_updates",
    ],
    "additionalProperties": False,
}


def _render_general_summary(meeting_name: str, d: dict) -> str:
    lines = [
        f"# {d['meeting_title'] or 'Biên bản họp'} — {meeting_name}",
        "",
        d["overview"],
    ]

    for sec in d["sections"]:
        lines += ["", f"## {sec['heading']}"]
        lines += [f"- {p}" for p in sec["points"]]

    if d["decisions"]:
        lines += ["", "## Quyết định"]
        for dec in d["decisions"]:
            lines.append(f"- **{dec['decision']}**")
            if dec["context"]:
                lines.append(f"  - {dec['context']}")

    if d["action_items"]:
        lines += ["", "## Action items"]
        for item in d["action_items"]:
            due = f" (deadline: {item['due']})" if item["due"] else ""
            owner = f" — **{item['owner']}**" if item["owner"] else ""
            lines.append(f"- [ ] {item['task']}{owner}{due}")

    if d["open_questions"]:
        lines += ["", "## Câu hỏi còn bỏ ngỏ"]
        lines += [f"- {q}" for q in d["open_questions"]]

    return "\n".join(lines) + "\n"


# ==========================================================================
# Client profile — online meeting with a customer or partner. Centered on
# what they want (requests), how they feel (feedback), and what each side
# committed to next (action_items).
# ==========================================================================
CLIENT_SCHEMA = {
    "type": "object",
    "properties": {
        "meeting_title": {"type": "string"},
        "counterpart": {"type": "string"},
        "overview": {"type": "string"},
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "points": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["heading", "points"],
                "additionalProperties": False,
            },
        },
        "requests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "request": {"type": "string"},
                    "context": {"type": "string"},
                },
                "required": ["request", "context"],
                "additionalProperties": False,
            },
        },
        "feedback": {"type": "array", "items": {"type": "string"}},
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": "string"},
                    "due": {"type": "string"},
                },
                "required": ["task", "owner", "due"],
                "additionalProperties": False,
            },
        },
        "knowledge_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["topic", "content"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "meeting_title", "counterpart", "overview", "topics",
        "requests", "feedback", "action_items", "knowledge_updates",
    ],
    "additionalProperties": False,
}


def _render_client_summary(meeting_name: str, d: dict) -> str:
    counterpart = d.get("counterpart") or "khách/partner"
    lines = [
        f"# {d['meeting_title'] or f'Họp với {counterpart}'} — {meeting_name}",
        "",
        f"**Khách/Partner:** {counterpart}",
        "",
        d["overview"],
    ]

    for topic in d["topics"]:
        lines += ["", f"## {topic['heading']}"]
        lines += [f"- {p}" for p in topic["points"]]

    if d["requests"]:
        lines += ["", "## Nhu cầu / yêu cầu từ khách"]
        for req in d["requests"]:
            lines.append(f"- **{req['request']}**")
            if req["context"]:
                lines.append(f"  - {req['context']}")

    if d["feedback"]:
        lines += ["", "## Phản hồi của khách"]
        lines += [f"- {f}" for f in d["feedback"]]

    if d["action_items"]:
        lines += ["", "## Action items / cam kết"]
        for item in d["action_items"]:
            due = f" (deadline: {item['due']})" if item["due"] else ""
            owner = f" — **{item['owner']}**" if item["owner"] else ""
            lines.append(f"- [ ] {item['task']}{owner}{due}")

    return "\n".join(lines) + "\n"


# ==========================================================================
# Registry
# ==========================================================================
PROFILES: dict[str, Profile] = {
    "sprint": Profile(
        name="sprint",
        label="Sprint meeting",
        prompt_file=SPRINT_PROMPT_FILE,
        schema=SPRINT_SCHEMA,
        render_summary=_render_sprint_summary,
        render_knowledge=lambda name, d: _render_knowledge("Sprint meeting", name, d["knowledge_updates"]),
    ),
    "client": Profile(
        name="client",
        label="Họp khách hàng / partner",
        prompt_file=CLIENT_PROMPT_FILE,
        schema=CLIENT_SCHEMA,
        render_summary=_render_client_summary,
        render_knowledge=lambda name, d: _render_knowledge("Họp khách/partner", name, d["knowledge_updates"]),
    ),
    "general": Profile(
        name="general",
        label="Buổi họp",
        prompt_file=GENERAL_PROMPT_FILE,
        schema=GENERAL_SCHEMA,
        render_summary=_render_general_summary,
        render_knowledge=lambda name, d: _render_knowledge("Buổi họp", name, d["knowledge_updates"]),
    ),
}


def get_profile(name: str) -> Profile:
    if name not in PROFILES:
        raise RuntimeError(
            f"Loại họp không hợp lệ: '{name}'. Chọn một trong: {', '.join(PROFILES)}"
        )
    return PROFILES[name]
