import argparse
import sys
from datetime import date
from pathlib import Path

import anthropic

from .config import KNOWLEDGE_FILE, MEETING_TYPE, RAW_DIR, TRANSCRIBE_BACKEND

# Windows terminals default to a legacy codepage (e.g. cp1252) that can't
# encode Vietnamese diacritics, crashing any print() of transcript/summary
# text. Force UTF-8 on stdout/stderr so console output never crashes on
# non-ASCII content, regardless of the terminal's active codepage.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _meeting_dir(arg: str | None, meeting_type: str | None) -> Path:
    """Raw working folder for a session: meetings/_raw/<profile>/<date>.
    An explicit path argument overrides the derived location."""
    if arg:
        return Path(arg)
    return RAW_DIR / (meeting_type or MEETING_TYPE) / date.today().isoformat()


def _transcribe(meeting_dir: Path) -> None:
    if TRANSCRIBE_BACKEND == "groq":
        from .transcribe_groq import transcribe_groq
        transcribe_groq(meeting_dir)
    else:
        from .transcribe import transcribe
        transcribe(meeting_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="meetings-agent",
        description="Record, transcribe, and summarize meetings (Slack huddles).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in [
        ("run", "record + transcribe + correct + summarize in one go (Ctrl+C stops recording)"),
        ("record", "record huddle audio until Ctrl+C"),
        ("transcribe", "transcribe recording.wav -> transcript.md + segments.json"),
        ("correct", "fix ASR errors using your glossary -> transcript_corrected.md"),
        ("summarize", "summarize transcript -> summary.md + knowledge.md"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("meeting_dir", nargs="?",
                       help="raw meeting folder (default: _raw/<type>/<today>)")
        p.add_argument(
            "--type", dest="meeting_type", default=None,
            help="meeting profile: auto | sprint | client | general "
                 "(auto = detect from transcript; default: MEETING_TYPE env, else auto)",
        )
        if name in ("summarize", "run"):
            p.add_argument(
                "--sprint", dest="sprint_number", default=None,
                help="sprint number for the monthly file (overrides the number "
                     "extracted from the transcript; sprint profile only)",
            )

    p_sync = sub.add_parser("sync", help="append knowledge.md to the shared knowledge file")
    p_sync.add_argument("meeting_dir", nargs="?",
                        help="raw meeting folder (default: _raw/<type>/<today>)")
    p_sync.add_argument("--type", dest="meeting_type", default=None,
                        help="meeting profile (to locate the raw folder)")
    p_sync.add_argument("--to", help="target knowledge file (default: KNOWLEDGE_FILE env var)")

    p_check = sub.add_parser(
        "check-audio",
        help="verify loopback + mic are capturing signal on the current default devices",
    )
    p_check.add_argument(
        "--duration", type=float, default=5.0, help="seconds to sample (default: 5)"
    )

    sub.add_parser("gui", help="launch the click-to-run desktop window")

    args = parser.parse_args()

    if args.command == "check-audio":
        from .diagnostics import check_audio
        # Same friendly handling as the commands below: on macOS/Linux with no
        # LOOPBACK_DEVICE set, loopback_source() raises the "install a virtual
        # audio device" message — and check-audio is exactly the command that
        # user runs first, so it must read that message, not a traceback.
        try:
            ok = check_audio(args.duration)
        except (FileNotFoundError, RuntimeError) as e:
            sys.exit(str(e))
        sys.exit(0 if ok else 1)

    if args.command == "gui":
        from .gui import launch_gui
        launch_gui()
        return

    meeting_dir = _meeting_dir(args.meeting_dir, args.meeting_type)

    try:
        if args.command == "record":
            from .audio import record
            record(meeting_dir)
        elif args.command == "transcribe":
            _transcribe(meeting_dir)
        elif args.command == "correct":
            from .correct import correct
            correct(meeting_dir)
        elif args.command == "summarize":
            from .summarize import summarize
            summarize(meeting_dir, args.meeting_type, args.sprint_number)
        elif args.command == "run":
            from .audio import record
            from .config import warn_if_no_api_key
            from .correct import correct
            from .summarize import summarize
            warn_if_no_api_key(meeting_dir)
            record(meeting_dir)
            _transcribe(meeting_dir)
            try:
                correct(meeting_dir)
            except (RuntimeError, anthropic.APIError) as e:
                print(f"\nWARNING: transcript correction failed ({e}) — summarizing the raw transcript instead.")
            summarize(meeting_dir, args.meeting_type, args.sprint_number)
            print("\nDone. Review the published summary, then run `meetings-agent sync` to update the knowledge base.")
        elif args.command == "sync":
            from .knowledge import sync
            target = args.to or KNOWLEDGE_FILE
            if not target:
                sys.exit("No target: pass --to <file> or set KNOWLEDGE_FILE in .env")
            sync(meeting_dir, Path(target))
    except (FileNotFoundError, RuntimeError) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
