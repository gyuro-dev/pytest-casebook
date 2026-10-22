"""A tiny CLI that prints a greeting."""

import argparse

parser = argparse.ArgumentParser(prog="greet")
parser.add_argument("--name", required=True)
parser.add_argument("--polite", action="store_true")
args = parser.parse_args()
print(f"Good day to you, {args.name}." if args.polite else f"Hi, {args.name}!")
