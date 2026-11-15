#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
repo='https://github.com/ricoxvl/PortfolioIQ.git'
printf 'Publish PortfolioIQ to PRIVATE GitHub repository: %s\n' "$repo"
read -r -p 'Run pre-publish safety check and push to GitHub? [y/N] ' reply
[[ "$reply" == [yY] ]] || { echo 'Cancelled'; exit 0; }
command -v git >/dev/null || { echo 'Git is required.' >&2; exit 1; }
command -v python3 >/dev/null || { echo 'Python 3 is required.' >&2; exit 1; }
[[ -d .git ]] || git init -b main
git symbolic-ref HEAD refs/heads/main
git add -A
python3 scripts/prepublish_check.py
if git remote get-url origin >/dev/null 2>&1; then
  actual="$(git remote get-url origin)"
  [[ "$actual" == "$repo" ]] || { printf 'Unexpected origin: %s\n' "$actual" >&2; exit 1; }
else
  git remote add origin "$repo"
fi
if ! git diff --cached --quiet; then
  git commit -m 'Build PortfolioIQ investment intelligence platform'
fi
git push -u origin main
printf '\nSuccess! Check: https://github.com/ricoxvl/PortfolioIQ/actions\n'
