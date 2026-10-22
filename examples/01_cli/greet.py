"""あいさつを出すだけの小さな CLI。"""

import argparse

parser = argparse.ArgumentParser(prog="greet")
parser.add_argument("--name", required=True)
parser.add_argument("--polite", action="store_true")
args = parser.parse_args()
print(f"こんにちは、{args.name}{'様' if args.polite else 'さん'}")
