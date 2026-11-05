#!/usr/bin/env bash
# Writes run_tests.py: about 3,000 lines of passing-test noise and two real failures.
set -eu
cat > run_tests.py <<'PY'
import sys
failures = {
    "test_parse_date": "AssertionError: expected '2024-02-29', got '2024-03-01'",
    "test_rounding": "AssertionError: expected 2.68, got 2.67 (round(2.675, 2))",
}
for i in range(1, 1501):
    name = "test_parse_date" if i == 612 else "test_rounding" if i == 1377 else f"test_case_{i:04d}"
    print(f"collecting tests/test_module_{i % 40:02d}.py::{name}")
    if name in failures:
        print(f"FAILED {name} - {failures[name]}")
    else:
        print(f"PASSED {name} [{i * 100 // 1500:3d}%] (0.0{i % 9}s)")
print(f"=========== 2 failed, 1498 passed in 4.21s ===========")
sys.exit(1)
PY
