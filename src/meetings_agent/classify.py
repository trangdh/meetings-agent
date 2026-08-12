"""Detect which meeting profile a transcript belongs to.

Used when the meeting type is left as "auto" (the default) — so a meeting
recorded without remembering to switch the profile still gets summarized
with the right structure and filed in the right place, instead of being
force-fit into the sprint layout.
"""

import json

from .config import CLAUDE_MODEL, anthropic_client

_SAMPLE_CHARS = 6000  # meeting type is almost always clear from the opening

_CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["sprint", "client", "general"]},
        "reason": {"type": "string"},
    },
    "required": ["type", "reason"],
    "additionalProperties": False,
}

_SYSTEM = """Bạn phân loại transcript một buổi họp của team vào ĐÚNG một loại:

- **sprint**: họp sprint nội bộ — tổng kết goal sprint vừa rồi, đi qua roadmap/epic/issue, sprint requests, và/hoặc phần dev+QA phân công issue + chốt sprint goal. Đặc trưng: nói về sprint, epic, issue, backlog, roadmap, phân công cho dev.
- **client**: họp với KHÁCH HÀNG hoặc PARTNER bên ngoài — demo, nghe nhu cầu/feedback của khách, bàn hợp tác. Đặc trưng: có người ngoài công ty, khách nêu yêu cầu tính năng, phản hồi về sản phẩm.
- **general**: mọi buổi họp nội bộ KHÁC không thuộc 2 loại trên — retro, brainstorm, họp bàn một chủ đề cụ thể, 1-1, v.v.

Đọc đoạn transcript và chọn loại khớp nhất. Nếu phân vân giữa sprint và general, chỉ chọn sprint khi rõ ràng có yếu tố sprint (goal/roadmap/issue/phân công). Trả về `type` và `reason` ngắn gọn (1 câu) giải thích vì sao."""


def detect_profile(transcript: str) -> tuple[str, str]:
    """Return (profile_name, reason). Falls back to 'general' on any error —
    a wrong 'general' pollutes less than wrongly merging into the sprint file."""
    sample = transcript[:_SAMPLE_CHARS]
    try:
        client = anthropic_client()
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            thinking={"type": "disabled"},
            system=_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _CLASSIFY_SCHEMA}},
            messages=[{"role": "user", "content": f"Transcript (trích đầu buổi):\n\n{sample}"}],
        )
        text = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(text)
        return data["type"], data.get("reason", "")
    except Exception as e:
        print(f"  [classify] không phân loại được ({e}) — mặc định 'general'.")
        return "general", "fallback do lỗi phân loại"
