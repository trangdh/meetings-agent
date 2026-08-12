#!/bin/bash
# Double-clickable launcher on macOS (Finder runs .command files in Terminal).
cd "$(dirname "$0")/.." || exit 1
exec .venv/bin/meetings-agent gui
