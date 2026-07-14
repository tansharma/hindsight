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
Label punctuation (":", "-", em/en dash, or nothing) and minor label
wording (e.g. "LLM Action Prompt" vs "Suggested LLM Action Prompt") are
tolerated; a new finding starts at each "Area" label.

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
    + r")\s*\*\*\s*[:\-–—]?\s*",
    re.IGNORECASE,
)


def parse_findings(text):
    matches = list(LABEL_PATTERN.finditer(text))
    if not matches:
        return []

    tagged = []
    for i, m in enumerate(matches):
        key = FIELD_ALIASES[m.group(1).lower()]
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = re.sub(r"\n{2,}", "\n\n", text[start:end]).strip()
        tagged.append((key, value))

    findings = []
    current = {}
    for key, value in tagged:
        if key == "Area" and current:
            findings.append(current)
            current = {}
        current[key] = value
    if current:
        findings.append(current)

    return [f for f in findings if all(f.get(k) for k in REQUIRED_KEYS)]


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as fh:
            text = fh.read()
    else:
        if sys.stdin.isatty():
            print("Error: no input file given and stdin is a terminal.", file=sys.stderr)
            return 1
        text = sys.stdin.read()

    findings = parse_findings(text)
    if not findings:
        print("Error: no complete Improvement findings could be parsed from input.", file=sys.stderr)
        return 1

    ordered = [{k: f[k] for k in REQUIRED_KEYS} for f in findings]
    print(json.dumps(ordered, indent=2))
    print(f"Parsed {len(ordered)} finding(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
