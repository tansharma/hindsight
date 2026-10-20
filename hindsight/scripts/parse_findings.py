#!/usr/bin/env python3
"""T4 test script: parses the unstructured architect review produced by
executing T3's P-Prompt into structured Improvement objects.

Usage:
    scripts/parse_findings.py < review.txt
    scripts/parse_findings.py path/to/review.txt

Input is the raw prose/markdown review, which per T3's "Output Format"
instruction lists findings one at a time using five labeled fields:
    **Area** ...
    **Issue** ...
    **Rationale** ...
    **Impact/Effort** ...
    **Suggested LLM Action Prompt** ...
Label punctuation (":", "-", em/en dash, or nothing — inside or after the
bold, so "**Area:**" and "**Area**:" both work) and minor label wording
(e.g. "LLM Action Prompt" vs "Suggested LLM Action Prompt") are tolerated.

A new finding starts at each "Area" label that begins a line (optionally
after a list marker, number, heading hashes, or ">"). Labels that appear
mid-line are accepted only for a field the current finding hasn't seen yet,
and labels inside fenced code blocks are ignored — so a field value (most
often the LLM prompt) that *mentions* "**Area**" or "**Issue**" is not
split into a bogus new finding or truncated.

Prints a JSON array of Improvement objects to stdout, each with exactly the
keys: Area, Issue, Rationale, Impact/Effort, LLM_Prompt.

Exit codes:
    0  at least one complete finding parsed, JSON array printed
    1  no input, or zero complete findings could be parsed
"""

import json
import re
import sys

FIELD_ALIASES = {
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

REQUIRED_KEYS = ["Area", "Issue", "Rationale", "Impact/Effort", "LLM_Prompt"]

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


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as fh:
            text = fh.read()
    else:
        if sys.stdin.isatty():
            print("Error: no input file given and stdin is a terminal.", file=sys.stderr)
            return 1
        text = sys.stdin.read()

    found = split_findings(text)
    findings = [f for f in found if is_complete(f)]
    incomplete = len(found) - len(findings)
    if incomplete:
        print(
            f"Warning: dropped {incomplete} incomplete finding(s) missing one of: "
            + ", ".join(REQUIRED_KEYS),
            file=sys.stderr,
        )
    if not findings:
        print("Error: no complete Improvement findings could be parsed from input.", file=sys.stderr)
        return 1

    ordered = [{k: f[k] for k in REQUIRED_KEYS} for f in findings]
    print(json.dumps(ordered, indent=2))
    print(f"Parsed {len(ordered)} finding(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
