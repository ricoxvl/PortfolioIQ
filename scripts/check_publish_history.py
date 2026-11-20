#!/usr/bin/env python3
"""Check all reachable Git history for selected high-confidence publication hazards.

Read-only, offline, no secret values printed. This is not an exhaustive security audit.
Works from a full clone (git fetch --all --tags; no shallow history).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 5_000_000
PATTERNS = {
    "OpenAI-style API credential": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "Anthropic-style API credential": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    "GitHub access token": re.compile(r"\b(?:ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{20,}\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "Private key header": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    "Hardcoded long secret field": re.compile(
        r"""(?i)\b(?:client_secret|api[_-]?secret|auth[_-]?token)\s*[:=]\s*["']([A-Za-z0-9._/-]{24,})["']"""
    ),
}
FORBIDDEN_SUFFIXES = (
    ".sqlite", ".sqlite3", ".db", ".dump", ".backup", ".pem", ".p12", ".pfx", ".key", ".kdbx"
)


def git(*args: str, stdin: bytes | None = None) -> bytes:
    process = subprocess.run(
        ["git", *args], cwd=ROOT, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if process.returncode:
        raise RuntimeError(
            f"git {' '.join(args)} failed: "
            + process.stderr.decode("utf-8", errors="replace")[:300]
        )
    return process.stdout


def blocked_path(path: str) -> bool:
    name = Path(path).name.lower()
    if name == ".env" or (name.startswith(".env.") and name not in {".env.example", ".env.beta.example"}):
        return True
    if name.endswith(FORBIDDEN_SUFFIXES):
        return True
    if name.endswith((".sqlite3-wal", ".sqlite3-shm")):
        return True
    return False


def main() -> int:
    try:
        shallow = git("rev-parse", "--is-shallow-repository").strip()
        if shallow == b"true":
            print("BLOCKED: shallow clone; cannot scan full reachable history.")
            return 2
        lines = git("rev-list", "--objects", "--all").decode("utf-8", errors="replace").splitlines()
        if not lines:
            print("BLOCKED: no Git objects found.")
            return 2
        paths: dict[str, str] = {}
        for line in lines:
            sha, _, path = line.partition(" ")
            paths.setdefault(sha, path or "<unnamed object>")
        batch_input = ("\n".join(paths) + "\n").encode()
        info = git("cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)", stdin=batch_input)
        problems: list[tuple[str, str]] = []
        blob_count = 0
        binary_count = 0
        oversized_count = 0
        for row in info.decode().splitlines():
            parts = row.split()
            if len(parts) != 3 or parts[1] != "blob":
                continue
            sha, _, raw_size = parts
            path = paths.get(sha, "<unknown>")
            size = int(raw_size)
            blob_count += 1
            if blocked_path(path):
                problems.append((path, "Historically committed protected file type/path"))
            if size > MAX_BYTES:
                oversized_count += 1
                continue
            blob = git("cat-file", "blob", sha)
            if b"\x00" in blob[:512]:
                binary_count += 1
                continue
            data = blob.decode("utf-8", errors="replace")
            for label, pattern in PATTERNS.items():
                if pattern.search(data):
                    problems.append((path, label))
        print(f"Historical Git blobs examined: {blob_count} total objects; "
              f"{binary_count} binary objects skipped; "
              f"{oversized_count} oversized objects skipped.")
        if problems:
            print("BLOCKED: possible publication hazards (values withheld):")
            for path, label in sorted(set(problems))[:80]:
                print(f"  - {path}: {label}")
            if len(set(problems)) > 80:
                print(f"  ... and {len(set(problems))-80} further findings")
            return 1
        print("PASS: no listed high-confidence secret patterns or protected file paths found "
              "in scanned reachable Git blobs.")
        print("LIMITATIONS: pattern coverage is incomplete; binary assets, oversized blobs, "
              "unreachable Git objects, public-data rights, and participant privacy "
              "still require manual review.")
        return 0
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"BLOCKED: history check could not finish: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
