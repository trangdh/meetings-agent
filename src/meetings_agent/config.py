import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT
MEETINGS_DIR = REPO_ROOT / "meetings"
# Raw working files (recording.wav + intermediate transcripts) live here,
# split by profile: _raw/<profile>/<date>/. The polished summaries land in
# the profile-organized layout under MEETINGS_DIR (see output_layout.py).
RAW_DIR = MEETINGS_DIR / "_raw"
SPRINT_PROMPT_FILE = PROJECT_ROOT / "prompts" / "sprint_summary.md"
CLIENT_PROMPT_FILE = PROJECT_ROOT / "prompts" / "client_meeting.md"
GENERAL_PROMPT_FILE = PROJECT_ROOT / "prompts" / "general_summary.md"
CORRECTION_PROMPT_FILE = PROJECT_ROOT / "prompts" / "transcript_correction.md"
# The glossary in this repo is a public template, but a real one is the
# opposite: it is team-specific, and only pays off if everyone who runs the
# agent shares — and keeps adding to — the same file. Overridable so that file
# can live wherever the team already shares things (next to KNOWLEDGE_FILE,
# say), instead of forcing a choice between a stale private copy per laptop
# and committing internal names into a repo meant to be published.
GLOSSARY_FILE = Path(os.getenv("GLOSSARY_FILE") or PROJECT_ROOT / "glossary.md")

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")
MEETING_TYPE = os.getenv("MEETING_TYPE", "auto")  # "auto" = detect from transcript; or sprint/client/general
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE") or None
# Default: append into a file inside meetings/ rather than anywhere in your
# own knowledge base sight-unseen. Override via --to or KNOWLEDGE_FILE.
KNOWLEDGE_FILE = os.getenv("KNOWLEDGE_FILE") or str(
    MEETINGS_DIR / "knowledge-updates.md"
)

# Name/substring of the input device to use as the loopback (system-audio)
# source. Windows doesn't need this — it uses real WASAPI loopback on the
# default speaker. macOS/Linux have no loopback API, so this must point at
# a virtual audio device (e.g. "BlackHole 2ch") — see README.
LOOPBACK_DEVICE = os.getenv("LOOPBACK_DEVICE") or None

TRANSCRIBE_BACKEND = os.getenv("TRANSCRIBE_BACKEND", "local")  # "local" | "groq"
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or None
GROQ_MODEL = os.getenv("GROQ_MODEL", "whisper-large-v3")

# Auto commit+push the published summary to GitHub after summarize.
AUTO_PUSH = os.getenv("AUTO_PUSH", "false").strip().lower() in ("1", "true", "yes")

SAMPLE_RATE = 16_000


_MISSING_KEY = "Thiếu ANTHROPIC_API_KEY — điền vào .env (xem .env.example)"


def require_api_key(recovery_hint: str = "") -> None:
    """Raise if ANTHROPIC_API_KEY is unset, with an actionable message.

    A missing key is not caught anywhere useful otherwise: the SDK constructs
    a client with api_key=None quite happily and only raises TypeError deep
    inside the first request ("Could not resolve authentication method"),
    which neither the CLI's `except (FileNotFoundError, RuntimeError)` nor
    `run`'s `except (RuntimeError, anthropic.APIError)` catches. The user
    would meet it as a traceback after an hour-long meeting. RuntimeError is
    what both the CLI and the GUI already know how to display.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(f"{_MISSING_KEY} rồi chạy lại.{recovery_hint}")


def warn_if_no_api_key(meeting_dir) -> None:
    """Say a missing key will stop the summary — without refusing to record.

    `run` does need the key for its last two steps, so saying so before the
    meeting is worth it. Refusing to start is not: the recording is the only
    part of this that cannot be redone, and trading it away to avoid re-running
    one command afterwards is the wrong way round. Warn, then record.
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        return
    print(
        f"\nWARNING: {_MISSING_KEY}.\n"
        "  Vẫn thu và transcribe bình thường — chỉ correct/summarize là dừng.\n"
        f"  Điền key xong thì chạy: meetings-agent summarize {meeting_dir}\n"
    )


def anthropic_client():
    """Anthropic client, refusing early if there is no key to use it with."""
    import anthropic  # lazy: keeps `import config` off the SDK's import cost

    # Every caller here runs after the meeting was recorded, so say so: the
    # failure looks alarming at a point where nothing is actually lost.
    require_api_key(
        " Recording và transcript đã lưu, không mất gì: chạy lại "
        "`meetings-agent summarize <meeting_dir>` là xong."
    )
    return anthropic.Anthropic()
