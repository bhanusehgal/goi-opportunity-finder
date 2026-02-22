"""Auto-commit and push eligible changes to GitHub.

Run once:
    python scripts/auto_publish.py

Watch mode:
    python scripts/auto_publish.py --watch
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import subprocess
import sys
import time
from typing import Iterable

EXCLUDED_EXACT = {
    ".env",
    "$null",
}

EXCLUDED_PREFIXES = (
    ".git/",
    "data/",
    ".pytest_cache/",
    ".venv/",
)

EXCLUDED_CONTAINS = (
    "/__pycache__/",
)

EXCLUDED_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".tmp",
)


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _normalize(path: str) -> str:
    return path.strip().strip('"').replace("\\", "/")


def _parse_status_line(line: str) -> str | None:
    if len(line) < 4:
        return None
    raw = line[3:].strip()
    if " -> " in raw:
        raw = raw.split(" -> ", 1)[1].strip()
    return _normalize(raw)


def _is_excluded(path: str) -> bool:
    normalized = _normalize(path)
    if not normalized:
        return True
    if normalized in EXCLUDED_EXACT:
        return True
    if any(normalized.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return True
    if any(token in normalized for token in EXCLUDED_CONTAINS):
        return True
    if any(normalized.endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
        return True
    return False


def _candidate_paths() -> list[str]:
    status = _run(["git", "status", "--porcelain"], check=True).stdout.splitlines()
    paths: list[str] = []
    for line in status:
        parsed = _parse_status_line(line)
        if not parsed:
            continue
        if _is_excluded(parsed):
            continue
        paths.append(parsed)
    # Preserve deterministic behavior.
    return sorted(set(paths))


def _stage_paths(paths: Iterable[str]) -> None:
    for path in paths:
        _run(["git", "add", "-A", "--", path], check=True)


def _has_staged_changes() -> bool:
    diff = _run(["git", "diff", "--cached", "--name-only"], check=True).stdout.strip()
    return bool(diff)


def _publish_once(remote: str, branch: str, message_prefix: str) -> bool:
    paths = _candidate_paths()
    if not paths:
        print("No eligible changes to publish.")
        return False

    print("Staging:")
    for path in paths:
        print(f"  - {path}")
    _stage_paths(paths)
    if not _has_staged_changes():
        print("Nothing staged after exclusions.")
        return False

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    message = f"{message_prefix} {timestamp}"
    _run(["git", "commit", "-m", message], check=True)
    _run(["git", "push", remote, branch], check=True)
    print(f"Pushed to {remote}/{branch}: {message}")
    return True


def _assert_git_identity() -> None:
    name = _run(["git", "config", "user.name"], check=False).stdout.strip()
    email = _run(["git", "config", "user.email"], check=False).stdout.strip()
    if not name or not email:
        raise RuntimeError(
            "Git identity is not set. Run: "
            "git config --global user.name \"Your Name\" && "
            "git config --global user.email \"you@example.com\""
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto commit + push helper")
    parser.add_argument("--remote", default="origin", help="Git remote name")
    parser.add_argument("--branch", default="main", help="Git branch name")
    parser.add_argument(
        "--message-prefix",
        default="auto: publish",
        help="Commit message prefix",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously watch and publish changes",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=20,
        help="Polling interval for --watch mode",
    )
    args = parser.parse_args()

    try:
        _assert_git_identity()
    except RuntimeError as exc:
        print(str(exc))
        return 1

    if not args.watch:
        try:
            _publish_once(
                remote=args.remote,
                branch=args.branch,
                message_prefix=args.message_prefix,
            )
            return 0
        except subprocess.CalledProcessError as exc:
            print(exc.stderr.strip() or str(exc))
            return exc.returncode

    print(
        f"Watching for changes every {args.interval_seconds}s. "
        "Press Ctrl+C to stop."
    )
    try:
        while True:
            try:
                _publish_once(
                    remote=args.remote,
                    branch=args.branch,
                    message_prefix=args.message_prefix,
                )
            except subprocess.CalledProcessError as exc:
                print(exc.stderr.strip() or str(exc))
            time.sleep(max(5, args.interval_seconds))
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
