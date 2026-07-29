"""Optionally commit + push a published summary to GitHub after summarize.

Enabled with AUTO_PUSH=true in .env. Deliberately conservative:
- Stages ONLY the given files (never `git add -A`), so it can't sweep up
  secrets, raw meeting content, or unrelated work.
- Runs at the repo root, rebases on the remote first to avoid clobbering
  concurrent pushes, and treats every failure as non-fatal — a push
  problem must never lose the summary that was just written.
"""

import subprocess
from pathlib import Path

from .config import REPO_ROOT


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )


def auto_push(paths: list[Path], message: str) -> None:
    """Stage `paths`, commit with `message`, rebase, and push. Best-effort."""
    if _git("rev-parse", "--is-inside-work-tree").returncode != 0:
        print("  [push] không phải git repo — bỏ qua auto-push.")
        return

    rels = [str(p) for p in paths if Path(p).exists()]
    if not rels:
        print("  [push] không có file summary để push.")
        return

    if _git("add", "--", *rels).returncode != 0:
        print("  [push] git add thất bại — bỏ qua.")
        return

    if _git("diff", "--cached", "--quiet").returncode == 0:
        print("  [push] summary không thay đổi so với bản đã commit — không cần push.")
        return

    if _git("commit", "-m", message).returncode != 0:
        print("  [push] git commit thất bại — bỏ qua.")
        return

    rebase = _git("pull", "--rebase")
    if rebase.returncode != 0:
        _git("rebase", "--abort")
        print("  [push] pull --rebase gặp xung đột — đã commit local, CHƯA push. "
              "Hãy tự pull/push thủ công.")
        return

    push = _git("push")
    if push.returncode != 0:
        print(f"  [push] git push thất bại: {push.stderr.strip()[:200]} "
              "— đã commit local, thử push lại thủ công.")
        return

    print(f"  [push] đã push summary lên GitHub ({message}).")
