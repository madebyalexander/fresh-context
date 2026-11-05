#!/usr/bin/env bash
# Every fresh-context check in one command. Prints only failures, then a pass line.
# Synthetic tests (the npx installer too, when node is installed), manifest checks, `claude plugin validate`, and linters if installed.
set -u
cd "$(dirname "$0")/.." || exit 1
fail=0
python3 tests/test_lean.py || fail=1
if command -v claude >/dev/null; then
  out=$(claude plugin validate . --strict 2>&1) || { echo "FAIL claude plugin validate"; echo "$out" | tail -n 15; fail=1; }
else echo "skip: claude CLI not found (plugin validate)"; fi
if command -v shellcheck >/dev/null; then
  shellcheck skills/working-lean/scripts/quiet tests/run.sh evals/*/scaffold.sh || fail=1
else echo "skip: shellcheck not installed"; fi
if command -v ruff >/dev/null; then
  ruff check --quiet --line-length 130 tests skills/working-lean/scripts/{jpick,outline,tokens,statusline.py,lean_hooks.py} || fail=1
else echo "skip: ruff not installed"; fi
[ "$fail" = 0 ] && echo "fresh-context: everything passed" || { echo "fresh-context: failures above"; exit 1; }
