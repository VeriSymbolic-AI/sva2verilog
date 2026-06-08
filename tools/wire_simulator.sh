#!/bin/bash
# Wire simulator fixture into all simulation test files
set -e

for f in tests/simulation/test_sim_*.py; do
  echo "Processing $f"
  # Add simulator: str to def test_* lines
  sed -i '' 's/\(def test_[a-zA-Z_]*([^)]*)\) -> None:/\1, simulator: str) -> None:/g' "$f"
  # Add simulator: str to def _run* lines with return type
  sed -i '' 's/\(def _run[a-zA-Z_]*([^)]*)\) ->/\1, simulator: str) ->/g' "$f"
  # Add simulator: str to def _run* lines without return type
  sed -i '' 's/\(def _run[a-zA-Z_]*([^)]*)\)):/\1, simulator: str):/g' "$f"
  # Add simulator: str to def _custom* lines
  sed -i '' 's/\(def _custom[a-zA-Z_]*([^)]*)\) ->/\1, simulator: str) ->/g' "$f"
  sed -i '' 's/\(def _custom[a-zA-Z_]*([^)]*)\)):/\1, simulator: str):/g' "$f"
  # Add simulator=simulator, to run_simulation calls
  sed -i '' 's/\(      rtl_out = run_simulation(\)/\1simulator=simulator,\n                /g' "$f"
  sed -i '' 's/\(          rtl_out = run_simulation(\)/\1simulator=simulator,\n                    /g' "$f"
  sed -i '' 's/\(      return run_simulation(\)/\1simulator=simulator,\n                       /g' "$f"
  sed -i '' 's/\(          return run_simulation(\)/\1simulator=simulator,\n                               /g' "$f"
done

echo "All files processed"
