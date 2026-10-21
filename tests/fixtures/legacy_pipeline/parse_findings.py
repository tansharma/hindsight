#!/usr/bin/env python3
"""Legacy pipeline (retired from the shipped skill; kept in
tests/fixtures/legacy_pipeline/ as tested reference code): turns the review
produced by executing build_prompt.sh's P-Prompt into a findings document
(the contract in hindsight/scripts/findings_schema.py). The live skill has
the agent write the findings document directly.

Usage:
    parse_findings.py < review.txt
    parse_findings.py path/to/review.txt

The P-Prompt asks the model for JSON. If the input is JSON — a findings
document, a bare array, or a needs-input document, optionally wrapped in
one ```json fence — it is validated and normalized. Otherwise it is parsed as the older prose format,
which lists findings one at a time using six labeled fields:
    **Area** ...
    **Issue** ...
    **Rationale** ...
    **Impact/Effort** ...
    **Suggested LLM Action Prompt** ...
    **Done When** ...
Label punctuation (":", "-", em/en dash, or nothing — inside or after the
bold, so "**Area:**" and "**Area**:" both work) and minor label wording
(e.g. "LLM Action Prompt" vs "Suggested LLM Action Prompt") are tolerated.

A new finding starts at each "Area" label that begins a line (optionally
after a list marker, number, heading hashes, or ">"). Labels that appear
mid-line are accepted only for a field the current finding hasn't seen yet,
and labels inside fenced code blocks are ignored — so a field value (most
often the LLM prompt) that *mentions* "**Area**" or "**Issue**" is not
split into a bogus new finding or truncated.

Prints the findings document as JSON to stdout. Incomplete findings
(including any without "Done When") are dropped with a stderr warning.

Exit codes:
    0  at least one complete finding parsed, document printed
    1  no input, or zero complete findings could be parsed
"""

import json
import os
import re
import sys

# The findings contract lives with the shipped scripts.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "hindsight", "scripts"))
from findings_schema import NEEDS_INPUT, load_document  # noqa: E402

FIELD_ALIASES = {
    "done when": "Done_When",
    "done-when": "Done_When",
    "done_when": "Done_When",
    "acceptance criteria": "Done_When",
    "area": "Area",
    "issue": "Issue",
    "rationale": "Rationale",
    "impact/effort": "Impact/Effort",
    "impact / effort": "Impact/Effort",
    "suggested llm action prompt": "LLM_Prompt",
    "llm action prompt": "LLM_Prompt",
    "llm_prompt": "LLM_Prompt",
    "llm prompt": "LLM_Prompt",
}

REQUIRED_KEYS = ["Area", "Issue", "Rationale", "Impact/Effort", "LLM_Prompt", "Done_When"]

WHOLE_FENCE = re.compile(r"\A```[\w-]*[ \t]*\n(.*)\n```\Z", re.S)

LABEL_PATTERN = re.compile(
    r"\*\*\s*("
    + "|".join(re.escape(k) for k in sorted(FIELD_ALIASES, key=len, reverse=True))
    + r")\s*[:\-–—]?\s*\*\*\s*[:\-–—]?\s*",
    re.IGNORECASE,
)

# What may precede a label for it to count as starting a line.
LINE_START_PREFIX = re.compile(r"[ \t]*(?:(?:[-*+>]|\d+[.)]|#{1,6})[ \t]+)?")

FENCE_LINE = re.compile(r"[ \t]*(`{3,}|~{3,})")


def fenced_ranges(text):
    """Return (start, end) character offsets of fenced code blocks."""
    ranges = []
    open_start = None
    open_fence = None
    offset = 0
    for line in text.splitlines(keepends=True):
        m = FENCE_LINE.match(line)
        if m:
            fence = m.group(1)
            if open_fence is None:
                open_start, open_fence = offset, fence
            elif fence[0] == open_fence[0] and len(fence) >= len(open_fence):
                ranges.append((open_start, offset + len(line)))
                open_start = open_fence = None
        offset += len(line)
    if open_fence is not None:
        ranges.append((open_start, len(text)))
    return ranges


def at_line_start(text, pos):
    line_begin = text.rfind("\n", 0, pos) + 1
    return LINE_START_PREFIX.fullmatch(text[line_begin:pos]) is not None


def value_end(text, m):
    """Where the previous field's value stops: the start of this label's line
    if the label begins one (so a "- " marker isn't left on the value)."""
    if at_line_start(text, m.start()):
        return text.rfind("\n", 0, m.start()) + 1
    return m.start()


def split_findings(text):
    """Return every finding found, complete or not."""
    fences = fenced_ranges(text)

    accepted = []
    seen = set()
    for m in LABEL_PATTERN.finditer(text):
        if any(start <= m.start() < end for start, end in fences):
            continue
        key = FIELD_ALIASES[m.group(1).lower()]
        if key == "Area" and seen and at_line_start(text, m.start()):
            seen = set()
        elif key in seen:
            continue
        seen.add(key)
        accepted.append((key, m))

    if not accepted:
        return []

    findings = []
    current = {}
    for i, (key, m) in enumerate(accepted):
        end = value_end(text, accepted[i + 1][1]) if i + 1 < len(accepted) else len(text)
        value = re.sub(r"\n{2,}", "\n\n", text[m.end():end]).strip()
        if key == "Area" and current:
            findings.append(current)
            current = {}
        current[key] = value
    if current:
        findings.append(current)

    return findings


def is_complete(finding):
    return all(finding.get(k) for k in REQUIRED_KEYS)


def parse_findings(text):
    return [f for f in split_findings(text) if is_complete(f)]


def as_json(text):
    """Return the parsed JSON if text is a JSON object/array (optionally in
    one surrounding code fence), else None."""
    stripped = text.strip()
    m = WHOLE_FENCE.match(stripped)
    if m:
        stripped = m.group(1).strip()
    if not stripped.startswith(("{", "[")):
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, (dict, list)) else None


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as fh:
            text = fh.read()
    else:
        if sys.stdin.isatty():
            print("Error: no input file given and stdin is a terminal.", file=sys.stderr)
            return 1
        text = sys.stdin.read()

    data = as_json(text)
    if data is None:
        found = split_findings(text)
        findings = [f for f in found if is_complete(f)]
        incomplete = len(found) - len(findings)
        if incomplete:
            print(
                f"Warning: dropped {incomplete} incomplete finding(s) missing one of: "
                + ", ".join(REQUIRED_KEYS),
                file=sys.stderr,
            )
        data = [{k: f[k] for k in REQUIRED_KEYS} for f in findings]

    try:
        doc, warnings = load_document(data)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)
    if doc["status"] == NEEDS_INPUT:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        print(f"Parsed a needs-input document (missing: {', '.join(doc['missing'])}).", file=sys.stderr)
        return 0
    if not doc["findings"]:
        print("Error: no complete Improvement findings could be parsed from input.", file=sys.stderr)
        return 1

    print(json.dumps(doc, indent=2, ensure_ascii=False))
    print(f"Parsed {len(doc['findings'])} finding(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
