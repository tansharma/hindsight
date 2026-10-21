#!/usr/bin/env python3
"""Weighted Decision Matrix Generator: renders a Markdown comparison table
for the candidate solutions proposed against the single most critical
finding in a Hindsight review (SKILL.md Step 4).

Usage:
    scripts/render_decision_matrix.py < candidates.json
    scripts/render_decision_matrix.py candidates.json
    echo '<JSON array>' | scripts/render_decision_matrix.py

Input is a JSON array of candidate solution objects, each with exactly the
keys: solution, impact, effort, argument. `impact` and `effort` are
integers 1-5 (1 = marginal/trivial, 5 = transformative/major undertaking).

This step is rendering, not analysis: candidates are not re-scored,
re-ranked, or invented here. Invalid candidates (missing fields, or
impact/effort outside 1-5) are dropped with a stderr warning rather than
silently coerced.

Exit codes:
    0  three or more valid candidates, table printed to stdout
    1  no input, invalid JSON, or fewer than three valid candidates remain
"""

import json
import sys

REQUIRED_KEYS = ["solution", "impact", "effort", "argument"]
MIN_CANDIDATES = 3


def valid_candidate(c):
    """True if c is an object with a non-empty solution and argument and
    integer (not bool) impact and effort in 1-5."""
    if not isinstance(c, dict):
        return False
    if not all(c.get(k) not in (None, "") for k in ("solution", "argument")):
        return False
    for k in ("impact", "effort"):
        v = c.get(k)
        if not isinstance(v, int) or isinstance(v, bool) or not (1 <= v <= 5):
            return False
    return True


def render(candidates):
    lines = [
        "| Solution Name | Estimated Impact (1-5) | Development Effort (1-5) | Argument |",
        "|---|---|---|---|",
    ]
    for c in candidates:
        solution = str(c["solution"]).replace("|", "\\|")
        argument = str(c["argument"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {solution} | {c['impact']} | {c['effort']} | {argument} |")
    return "\n".join(lines) + "\n"


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as fh:
            raw = fh.read()
    else:
        if sys.stdin.isatty():
            print("Error: no input file given and stdin is a terminal.", file=sys.stderr)
            return 1
        raw = sys.stdin.read()

    if not raw.strip():
        print("Error: no input candidates provided.", file=sys.stderr)
        return 1

    try:
        candidates = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error: input is not valid JSON: {e}", file=sys.stderr)
        return 1

    if not isinstance(candidates, list):
        print("Error: input JSON must be an array of candidate solutions.", file=sys.stderr)
        return 1

    dropped = sum(1 for c in candidates if not valid_candidate(c))
    if dropped:
        print(
            f"Warning: dropped {dropped} candidate(s) missing a required "
            f"field or with impact/effort outside 1-5.",
            file=sys.stderr,
        )
    kept = [c for c in candidates if valid_candidate(c)]

    if len(kept) < MIN_CANDIDATES:
        print(
            f"Error: need at least {MIN_CANDIDATES} valid candidates, got {len(kept)}.",
            file=sys.stderr,
        )
        return 1

    print(render(kept))
    print(f"Rendered {len(kept)} candidate(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
