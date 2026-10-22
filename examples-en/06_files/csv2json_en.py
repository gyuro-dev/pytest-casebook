"""A CLI that reads a CSV file and writes it out as JSON."""

import csv
import json
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
with src.open(encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))
dst.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {len(rows)} row(s) to {dst}")
