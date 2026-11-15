#!/usr/bin/env python3
"""Fail fast if a planned PortfolioIQ source release contains secrets or user data.

This is a lightweight safety net, not a substitute for git history scanning,
secret scanning on GitHub, or an independent security assessment.
"""
from __future__ import annotations
from fnmatch import fnmatch
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {'.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache', 'dist', '.mypy_cache'}
EXCLUDE_FILES = {'.DS_Store'}
BLOCKED_SUFFIXES = {'.sqlite3', '.pem', '.p12', '.pfx', '.key', '.kdbx'}
SECRETS = {
    'OpenAI API key': re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b'),
    'GitHub token': re.compile(r'\b(?:ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{20,}\b'),
    'Private key': re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----'),
    'AWS access key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
}


def safe_to_publish(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    parts = relative.parts
    if any(piece in EXCLUDE_DIRS for piece in parts):
        return False
    if path.name in EXCLUDE_FILES:
        return False
    if path.name == '.env' or (path.name.startswith('.env.') and path.name != '.env.example'):
        return False
    if path.suffix.lower() in BLOCKED_SUFFIXES or path.name.endswith(('.sqlite3-wal', '.sqlite3-shm')):
        return False
    if len(parts) >= 3 and parts[:2] == ('backend', 'data') and path.name.endswith('.db'):
        return False
    return True


def git_tracked_files():
    try:
        output = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z'], stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return [ROOT / name.decode('utf-8') for name in output.split(b'\0') if name]


def main():
    candidates = git_tracked_files()
    if candidates is None:
        candidates = [p for p in ROOT.rglob('*') if p.is_file() and safe_to_publish(p)]
        mode = 'working source (not yet a Git repository)'
    else:
        mode = 'Git-tracked files'
    problems = []
    inspected = 0
    for path in sorted(candidates):
        if not path.exists():
            continue
        if not safe_to_publish(path):
            problems.append(f'Excluded/generated file is Git-tracked: {path.relative_to(ROOT)}')
            continue
        if path.stat().st_size > 5_000_000:
            continue
        try:
            content = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        inspected += 1
        for label, regex in SECRETS.items():
            if regex.search(content):
                problems.append(f'{path.relative_to(ROOT)} contains a possible {label}')
    print(f'PortfolioIQ pre-publish check: {inspected} text files examined ({mode}).')
    if problems:
        print('BLOCKED:')
        for problem in problems:
            print('  - ' + problem)
        return 1
    print('PASS: no obvious secrets or generated databases selected for publication.')
    print('Note: configure GitHub push protection and review Git history before publication.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
