#!/usr/bin/env python3
"""Copies an eval fixture project to a destination and plants what must
never be committed to this repository: secret-looking files and injected
instructions (the "plant" section of the fixture's expected.json).

Usage:
    tests/eval/plant.py --expected tests/eval/fixtures/orders-svc.expected.json --dest <dir>

The destination must not exist yet.
"""

import argparse
import json
import os
import shutil
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", required=True)
    parser.add_argument("--dest", required=True)
    args = parser.parse_args()

    with open(args.expected, "r", encoding="utf-8") as fh:
        expected = json.load(fh)
    source = os.path.join(os.path.dirname(os.path.abspath(args.expected)), expected["fixture"])
    if os.path.exists(args.dest):
        print(f"Error: --dest '{args.dest}' already exists.", file=sys.stderr)
        return 1
    shutil.copytree(source, args.dest, ignore=shutil.ignore_patterns("__pycache__"))

    plant = expected.get("plant", {})
    for rel, content in plant.get("files", {}).items():
        with open(os.path.join(args.dest, rel), "w", encoding="utf-8") as fh:
            fh.write(content)
    for rel, replacements in plant.get("replace", {}).items():
        path = os.path.join(args.dest, rel)
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        for placeholder, value in replacements.items():
            if placeholder not in text:
                print(f"Error: placeholder {placeholder!r} not found in {rel}.", file=sys.stderr)
                return 1
            text = text.replace(placeholder, value)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(f"Planted {expected['fixture']} at {args.dest}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
