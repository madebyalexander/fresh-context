#!/usr/bin/env bash
# Writes big_module.py: about 6,000 lines of filler with normalize_amount in the middle.
set -eu
python3 - <<'PY'
lines = ['"""Generated module for the find-function-in-large-file eval."""', ""]
for i in range(1, 1201):
    lines += [f"def helper_{i:04d}(value):", f'    """Helper number {i}."""', f"    return value * {i % 7 + 1} + {i}", "", ""]
    if i == 640:
        lines += ["def normalize_amount(amount):",
                  '    """Round to cents; refunds are recorded elsewhere, so a negative amount becomes 0."""',
                  "    if amount < 0:", "        return 0.0", "    return round(float(amount), 2)", "", ""]
open("big_module.py", "w").write("\n".join(lines) + "\n")
PY
