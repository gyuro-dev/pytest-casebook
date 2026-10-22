"""A CLI that counts words."""

import sys
from collections import Counter

words = sys.stdin.read().split()
for word, count in sorted(Counter(words).items()):
    print(f"{word}: {count}")
if not words:
    print("No words found", file=sys.stderr)
    sys.exit(1)
