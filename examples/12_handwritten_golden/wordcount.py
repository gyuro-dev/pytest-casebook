"""単語を数える CLI。"""

import sys
from collections import Counter

words = sys.stdin.read().split()
for word, count in sorted(Counter(words).items()):
    print(f"{word}: {count}")
if not words:
    print("単語がありません", file=sys.stderr)
    sys.exit(1)
