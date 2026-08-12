#!/bin/bash
# One-command macOS setup, checking its own work at every step.
#
# The README's setup has six steps and three of them fail without an error
# message: BlackHole is invisible until coreaudiod restarts, system audio that
# is not routed through the virtual device records as silence, and a denied
# Microphone permission returns zeros rather than raising. So this does not
# just print instructions — it verifies each step actually took effect, and for
# the two steps macOS will not let a script perform, it waits and re-checks
# until the person has done them.
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$REPO/.venv"
PY_MIN_MINOR=10
cd "$REPO" || exit 1

ok()   { printf '      \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '      \033[33m!\033[0m %s\n' "$1"; }
die()  { printf '      \033[31m✗\033[0m %s\n' "$1"; exit 1; }
step() { printf '\n\033[1m[%s/6]\033[0m %s\n' "$1" "$2"; }

[ "$(uname)" = "Darwin" ] || die "This script is for macOS. On Windows follow the README instead."

# -------------------------------------------------- 1. venv + dependencies
# The environment comes first so every later check runs against the
# interpreter that will actually run the agent, not whatever python3 happens
# to be on PATH — those are routinely different versions with different
# modules available.
# Whatever is first on PATH as `python3` is not necessarily usable: on this
# machine it is a Homebrew 3.14 whose platform.mac_ver() returns empty, which
# makes uv refuse it outright and breaks the ensurepip step of `python -m venv`.
# So audit the candidates instead of trusting the name, newest usable first.
usable_python() {
    for name in python3.13 python3.12 python3.11 python3; do
        candidate=$(command -v "$name" 2>/dev/null) || continue
        "$candidate" - "$PY_MIN_MINOR" <<'PY' >/dev/null 2>&1 || continue
import platform, sys
assert sys.version_info >= (3, int(sys.argv[1]))
assert platform.mac_ver()[0], "reports no macOS version; uv and ensurepip both choke on this"
PY
        echo "$candidate"
        return 0
    done
    return 1
}

step 1 "Virtual environment and dependencies"
if [ ! -d "$VENV" ]; then
    BOOTSTRAP=$(usable_python || true)
    if [ -n "$BOOTSTRAP" ] && command -v uv >/dev/null && uv venv --python "$BOOTSTRAP" "$VENV" >/dev/null 2>&1; then
        ok "created .venv with uv ($("$BOOTSTRAP" --version))"
    elif [ -n "$BOOTSTRAP" ] && "$BOOTSTRAP" -m venv "$VENV" 2>/dev/null; then
        ok "created .venv with $("$BOOTSTRAP" --version)"
    elif command -v uv >/dev/null && uv venv "$VENV" >/dev/null 2>&1; then
        # No healthy interpreter on PATH, but uv will fetch its own.
        ok "created .venv with an interpreter uv provided ($("$VENV/bin/python" --version))"
    else
        rm -rf "$VENV"
        die "could not create a virtual environment. No usable Python 3.$PY_MIN_MINOR+ was found
      (a Homebrew python3 that reports no macOS version cannot bootstrap pip and is
      rejected by uv). Either 'brew install uv' and re-run, or install Python from
      python.org."
    fi
fi
PYTHON="$VENV/bin/python"
[ -x "$PYTHON" ] || die "$VENV exists but has no python in it. Delete the folder and re-run."
PY_MINOR=$("$PYTHON" -c 'import sys; print(sys.version_info.minor)')
[ "$PY_MINOR" -ge "$PY_MIN_MINOR" ] || die ".venv runs Python 3.$PY_MINOR; 3.$PY_MIN_MINOR+ is required. Delete .venv and re-run."

# A venv made by `uv` has no pip binary in it, and one made by `python -m venv`
# does — so ask, in order, rather than assuming either.
install_deps() {
    if [ -x "$VENV/bin/pip" ]; then
        "$VENV/bin/pip" install -q -e "$REPO"
    elif "$PYTHON" -m pip --version >/dev/null 2>&1; then
        "$PYTHON" -m pip install -q -e "$REPO"
    elif command -v uv >/dev/null; then
        uv pip install --python "$PYTHON" -q -e "$REPO"
    else
        "$PYTHON" -m ensurepip --upgrade >/dev/null 2>&1 &&
            "$PYTHON" -m pip install -q -e "$REPO"
    fi
}
install_deps || die "could not install dependencies into $VENV."
ok "$("$PYTHON" --version) with dependencies (editable install — keep this folder where it is)"

# ---------------------------------------------------------------- 2. tkinter
step 2 "tkinter (needed by the GUI only)"
if "$PYTHON" -c 'import tkinter' 2>/dev/null; then
    ok "present"
else
    warn "missing — Homebrew's Python ships without it, so 'meetings-agent gui' would fail on import."
    if command -v brew >/dev/null; then
        echo "      installing python-tk@3.$PY_MINOR to match .venv..."
        brew install "python-tk@3.$PY_MINOR" || warn "install failed — the CLI still works, only the GUI needs this."
    else
        warn "no Homebrew here; install Python from python.org to get tkinter. CLI works without it."
    fi
fi

# ------------------------------------------------------------- 3. BlackHole
step 3 "BlackHole (routes system audio so the agent can hear the meeting)"
has_blackhole() {
    "$PYTHON" - <<'PY' 2>/dev/null
import subprocess, sys
out = subprocess.run(["system_profiler", "SPAudioDataType"], capture_output=True, text=True).stdout
sys.exit(0 if "BlackHole" in out else 1)
PY
}
if has_blackhole; then
    ok "installed"
else
    command -v brew >/dev/null || die "Homebrew not found. Install BlackHole from https://existential.audio/blackhole/ then re-run."
    echo "      installing (asks for your password — it is an audio driver)..."
    brew install blackhole-2ch || die "install failed."
    # A driver installed while coreaudiod is already running stays invisible to
    # every audio API until the daemon restarts. This is the step people miss.
    echo "      restarting coreaudiod so the new driver is picked up..."
    sudo killall coreaudiod || true
    sleep 3
    has_blackhole && ok "installed and visible" || die "BlackHole still not visible. Try 'sudo killall coreaudiod' again, or reboot."
fi

# ------------------------------------------------------------------- 4. .env
step 4 "Configuration"
[ -f .env ] || { cp .env.example .env && ok "created .env from .env.example"; }
env_value() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2-; }
set_env() {  # set_env KEY VALUE — replace the line if present, else append
    if grep -qE "^#? *$1=" .env; then
        "$PYTHON" - "$1" "$2" <<'PY'
import re, sys
key, value = sys.argv[1], sys.argv[2]
text = open(".env", encoding="utf-8").read()
text = re.sub(rf"^#? *{re.escape(key)}=.*$", f"{key}={value}", text, count=1, flags=re.M)
open(".env", "w", encoding="utf-8").write(text)
PY
    else
        printf '%s=%s\n' "$1" "$2" >> .env
    fi
}

if [ -z "$(env_value ANTHROPIC_API_KEY)" ]; then
    echo "      ANTHROPIC_API_KEY is empty. Needed by 'correct' and 'summarize';"
    echo "      'record' and 'transcribe' work without it. Get one at console.anthropic.com."
    printf '      Paste it (or press Enter to skip): '
    read -r key
    [ -n "$key" ] && { set_env ANTHROPIC_API_KEY "$key"; ok "saved"; } || warn "skipped — fill it into .env before summarizing."
else
    ok "ANTHROPIC_API_KEY present"
fi
[ -n "$(env_value LOOPBACK_DEVICE)" ] || { set_env LOOPBACK_DEVICE "BlackHole 2ch"; }
ok "LOOPBACK_DEVICE=$(env_value LOOPBACK_DEVICE)"

# ------------------------------------------------- 5. audio routing + 6. test
# These two are one loop: rather than matching device names — which the person
# is free to change — play a sound and see whether the loopback channel hears
# it. That is the only check that cannot be satisfied by a setup that looks
# right and records nothing.
step 5 "Audio routing"
cat <<'EOF'
      Create a Multi-Output Device so you can hear the meeting AND record it:
        1. Open Audio MIDI Setup (Spotlight: "Audio MIDI Setup")
        2. Bottom-left "+" -> Create Multi-Output Device
        3. Tick BOTH your speakers/headphones AND "BlackHole 2ch"
           (set your speakers as Master Device, tick Drift Correction on BlackHole)
        4. System Settings -> Sound -> Output -> select it
      Leave it selected: `meetings-agent watch` records without warning you first.
EOF

step 6 "Verifying both channels really capture"
attempt=1
while true; do
    printf '\n      Playing a test sound and listening on both channels...\n'
    ( sleep 2; say -r 160 "Testing the meetings agent audio setup." >/dev/null 2>&1 ) &
    if "$VENV/bin/meetings-agent" check-audio --duration 7; then
        break
    fi
    printf '\n      Not there yet (attempt %s).\n' "$attempt"
    echo "      - No loopback signal  -> Output is not the Multi-Output Device yet (step 5)."
    echo "      - No mic signal       -> grant Microphone permission: System Settings >"
    echo "                               Privacy & Security > Microphone, enable it for this"
    echo "                               terminal app, then QUIT AND REOPEN the terminal and"
    echo "                               re-run this script (the permission only applies to a"
    echo "                               freshly launched app)."
    # Retrying is only meaningful if someone is there to fix the setup between
    # attempts. Piped or backgrounded, this would spin forever playing sounds.
    [ -t 0 ] || die "No terminal to prompt on — finish step 5 and run this script again."
    printf '      Press Enter to test again, or Ctrl+C to stop: '
    read -r _
    attempt=$((attempt + 1))
done

printf '\n\033[1mSetup complete.\033[0m Both channels are capturing.\n'
cat <<EOF

  $VENV/bin/meetings-agent run     # record a meeting end to end, Ctrl+C to stop
  $VENV/bin/meetings-agent gui     # or click buttons instead

Shorter, if you want it:
  echo "alias ma='$VENV/bin/meetings-agent'" >> ~/.zshrc && source ~/.zshrc
EOF
