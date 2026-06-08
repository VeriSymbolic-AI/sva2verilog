#!/usr/bin/env python3
"""Wire simulator fixture into all simulation test files."""
import re, sys, glob


def update_file(fpath):
    with open(fpath) as f:
        lines = f.readlines()

    changed = False
    new_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # 1. Add simulator: str to def lines
        if re.match(r'def (test_|_run|_custom)\w+\(', line):
            if 'simulator' not in line:
                line = re.sub(
                    r'(\))\s*(->\s*None\s*:|->|:)',
                    r', simulator: str)\2',
                    line
                )
                changed = True

        # 2. Add simulator=simulator, before run_simulation() call
        # Match a line that is just "run_simulation("
        stripped = line.lstrip()
        if stripped.startswith('run_simulation(') or stripped == 'rtl_out = run_simulation(' or stripped == 'return run_simulation(':
            # Get the indentation
            indent = line[:len(line) - len(stripped)]
            # Check if simulator is already in any of the next few lines
            has_sim = 'simulator=' in line
            j = i + 1
            while j < len(lines) and 'simulator=' not in lines[j] and j < i + 15:
                j += 1
            if j < i + 15 and 'simulator=' in lines[j]:
                has_sim = True

            if not has_sim:
                new_lines.append(f"{indent}simulator=simulator,\n")
                changed = True

        new_lines.append(line)
        i += 1

    if changed:
        with open(fpath, 'w') as f:
            f.writelines(new_lines)
        return True
    return False


files = sys.argv[1:]
if not files:
    files = sorted(glob.glob("tests/simulation/test_sim_*.py")) + ["tests/test_optimizer.py"]

for f in files:
    if update_file(f):
        print(f"Updated {f}")
    else:
        print(f"Skipped {f}")
