"""A small CLI that greets in Japanese or English (chosen with --lang)."""

import argparse

TEXTS = {
    "ja": {"hello": "こんにちは、{name}さん", "bye": "さようなら、{name}さん"},
    "en": {"hello": "Hello, {name}", "bye": "Goodbye, {name}"},
}

parser = argparse.ArgumentParser(prog="hello")
parser.add_argument("--lang", choices=sorted(TEXTS), default="en")
parser.add_argument("--bye", action="store_true")
parser.add_argument("name")
args = parser.parse_args()
print(TEXTS[args.lang]["bye" if args.bye else "hello"].format(name=args.name))
