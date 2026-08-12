"""Start recording when a Slack huddle starts, and run the pipeline when it ends.

Slack has no API for a bot to join a huddle or read its audio — that is why
recording happens on a participant's machine at all (see README). But whether
*you* are currently in a huddle IS available: `users.profile.get` returns a
`huddle_state` field, and it is cheap to ask (Tier 4, 100+ requests/minute), so
polling it every few seconds is enough to know when to press record.

This watches that field and drives the same `record()` the CLI uses, through
the `.stop` sentinel it already supports for exactly this purpose.
"""

import json
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from .config import MEETING_TYPE, RAW_DIR, SLACK_TOKEN

_API = "https://slack.com/api/users.profile.get"
_POLL_SECONDS = 10
# Slack's value while in a huddle. Anything else (typically "default_unset")
# means not in one — matched positively so an unknown future value reads as
# "not in a huddle" and the watcher stays quiet instead of recording forever.
_IN_HUDDLE = "in_a_huddle"
# Joining a huddle to say one sentence and leaving is not a meeting. Below this
# there is nothing worth transcribing, and summarizing it would spend API calls
# on noise.
_MIN_MEETING_SECONDS = 60
# A failing poll must not end the watch: laptops sleep, wifi drops, Slack has
# outages. Keep asking, but say so once rather than every 10 seconds.
_ERROR_QUIET_SECONDS = 300


class SlackAuthError(RuntimeError):
    """The token or its scopes are wrong. Polling again will not fix it.

    Separate from every other Slack failure because those — rate limits, 5xx,
    a dropped connection — are worth waiting out, and this one never is.
    Subclasses RuntimeError so the CLI prints it as a single line like the rest.
    """


def huddle_state(token: str) -> str:
    """Return the caller's raw `huddle_state` string."""
    req = urllib.request.Request(
        _API,
        data=urllib.parse.urlencode({}).encode(),
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.load(resp)

    if not payload.get("ok"):
        error = payload.get("error", "unknown_error")
        if error in ("invalid_auth", "not_authed", "account_inactive", "token_revoked"):
            raise SlackAuthError(
                f"Slack rejected SLACK_TOKEN ({error}) — check the token in .env."
            )
        if error == "missing_scope":
            raise SlackAuthError(
                "SLACK_TOKEN is missing the `users.profile:read` scope — add it to the "
                "Slack app, then reinstall the app to the workspace to get a new token."
            )
        raise RuntimeError(f"Slack API returned an error: {error}")

    return payload.get("profile", {}).get("huddle_state", "")


def _meeting_dir() -> Path:
    """A folder per huddle, not per day: two huddles in one afternoon are two
    meetings, and output_layout keys each published entry off this name."""
    started = datetime.now()
    return RAW_DIR / MEETING_TYPE / f"{started:%Y-%m-%d-%H%M}"


def _record_until(meeting_dir: Path, ended: threading.Event) -> float:
    """Record in a thread and stop it the moment `ended` is set.

    record() polls for a `.stop` file precisely so a supervising process can
    end it without a signal, which is what this is. Returns seconds recorded.
    """
    from .audio import record

    failure: list[BaseException] = []

    def target():
        try:
            record(meeting_dir)
        except BaseException as e:  # re-raised below, on the watcher's thread
            failure.append(e)

    started = time.monotonic()
    thread = threading.Thread(target=target, name="record", daemon=True)
    thread.start()

    while thread.is_alive() and not ended.is_set():
        ended.wait(1)
    meeting_dir.mkdir(parents=True, exist_ok=True)
    (meeting_dir / ".stop").touch()
    thread.join(timeout=30)

    if failure:
        raise failure[0]
    return time.monotonic() - started


def _process(meeting_dir: Path) -> None:
    """transcribe -> correct -> summarize, the same sequence `run` uses."""
    from .cli import _transcribe
    from .correct import correct
    from .summarize import summarize

    _transcribe(meeting_dir)
    try:
        correct(meeting_dir)
    except Exception as e:
        print(f"  WARNING: transcript correction failed ({e}) — summarizing the raw transcript.")
    summarize(meeting_dir)


def watch() -> None:
    """Poll Slack until interrupted, recording each huddle as it happens."""
    if not SLACK_TOKEN:
        raise RuntimeError(
            "SLACK_TOKEN is not set — create a Slack app with the `users.profile:read` "
            "scope and put its token in .env (see the README, "
            "'Tự động thu khi vào huddle')."
        )

    # Fail here rather than at the first huddle: this is the moment someone is
    # watching the terminal, and it also proves the token works.
    state = huddle_state(SLACK_TOKEN)
    print(f"Watching Slack for huddles (polling every {_POLL_SECONDS}s). Ctrl+C to stop.")
    print(f"  current state: {state or '(empty)'}")
    if not state:
        # Without a `user` argument the API answers about whoever the token
        # belongs to. A bot user is never in a huddle and its profile carries
        # no huddle_state at all, so a bot token makes this command sit there
        # forever recording nothing. Say it now rather than at the end of an
        # unrecorded week.
        print("  WARNING: this profile has no huddle_state field, which is what a bot token\n"
              "  returns — it reads the bot's own profile, and a bot is never in a huddle.\n"
              "  Use a user token (xoxp-...) for the account that joins the huddles.")
    if state == _IN_HUDDLE:
        print("  NOTE: you are already in a huddle — this one is not recorded, only the next.")

    was_in_huddle = state == _IN_HUDDLE
    last_error_at = 0.0
    while True:
        time.sleep(_POLL_SECONDS)
        try:
            state = huddle_state(SLACK_TOKEN)
        except SlackAuthError:
            raise
        except Exception as e:
            now = time.monotonic()
            if now - last_error_at > _ERROR_QUIET_SECONDS:
                print(f"  [watch] Slack unreachable ({e!r}) — still trying every {_POLL_SECONDS}s.")
                last_error_at = now
            continue

        in_huddle = state == _IN_HUDDLE
        if in_huddle == was_in_huddle:
            continue
        was_in_huddle = in_huddle
        if not in_huddle:
            continue

        meeting_dir = _meeting_dir()
        print(f"\n=== Huddle started — recording to {meeting_dir} ===")
        print("    Tell the others in the huddle that they are being recorded.")
        ended = threading.Event()

        def until_huddle_ends():
            while not ended.is_set():
                ended.wait(_POLL_SECONDS)
                try:
                    if huddle_state(SLACK_TOKEN) != _IN_HUDDLE:
                        ended.set()
                except Exception:
                    continue  # a dropped poll must not cut the recording short

        threading.Thread(target=until_huddle_ends, daemon=True).start()
        was_in_huddle = False
        # One bad huddle must not end the watch. This is meant to be left
        # running unattended, so a mic that got unplugged or a summary that
        # failed costs that meeting, not every meeting after it.
        try:
            seconds = _record_until(meeting_dir, ended)
        except Exception as e:
            print(f"  WARNING: recording this huddle failed ({e!r}) — still watching.")
            continue
        finally:
            ended.set()

        print(f"=== Huddle ended after {seconds / 60:.1f} minutes ===")
        if seconds < _MIN_MEETING_SECONDS:
            print(f"    Under {_MIN_MEETING_SECONDS}s — audio kept, skipping transcribe/summarize.")
            continue
        try:
            _process(meeting_dir)
        except Exception as e:
            print(f"  WARNING: processing failed ({e!r}) — audio and any transcript are in "
                  f"{meeting_dir}, re-run by hand. Still watching.")
            continue
        print("\nDone. Back to watching for the next huddle.")
