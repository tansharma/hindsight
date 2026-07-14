#!/usr/bin/env python3
"""T5 test script: renders the structured Improvement findings produced by
T4 (scripts/parse_findings.py) into the final deliverable, inHindsight.md.

Usage:
    scripts/parse_findings.py review.txt | \
      scripts/render_output.py --root <path> --goal "<use case>"
    # or
    scripts/render_output.py --root <path> --goal "<use case>" findings.json

Input is the JSON array of Improvement objects T4 produces, each with
exactly the keys: Area, Issue, Rationale, Impact/Effort, LLM_Prompt.

Writes the rendered markdown to `<root>/inHindsight.md` (or --out, if
given) and also prints it to stdout. This step is rendering, not analysis
or re-judging — every finding in the input appears in the output exactly
once, grouped and formatted, with no findings added, dropped, or reworded.

Exit codes:
    0  inHindsight.md written
    1  no input, invalid JSON, or zero findings to render
"""

import argparse
import json
import sys
from collections import OrderedDict
from datetime import date

# Priority order: quick wins first, then strategic bets, then easy cleanup,
# then lowest priority. Matches project.md's Impact/Effort decision matrix.
IMPACT_EFFORT_ORDER = [
    "High Impact / Low Effort",
    "High Impact / High Effort",
    "Low Impact / Low Effort",
    "Low Impact / High Effort",
]

IMPACT_EFFORT_LABELS = {
    "High Impact / Low Effort": "⚡ High Impact / Low Effort",
    "High Impact / High Effort": "\U0001f3d7️ High Impact / High Effort",
    "Low Impact / Low Effort": "\U0001f9f9 Low Impact / Low Effort",
    "Low Impact / High Effort": "\U0001f551 Low Impact / High Effort",
}

AREA_ORDER = ["Architectural Patterns", "Code Quality", "Documentation Gaps"]

HEADING_MAX_LEN = 90


def heading_text(issue):
    first_line = issue.splitlines()[0] if issue else ""
    if len(first_line) <= HEADING_MAX_LEN:
        return first_line
    cut = first_line[:HEADING_MAX_LEN].rsplit(" ", 1)[0]
    return f"{cut}…"


def normalize_area(area):
    lowered = area.lower()
    if "architect" in lowered:
        return "Architectural Patterns"
    if "doc" in lowered:
        return "Documentation Gaps"
    if "code" in lowered or "quality" in lowered:
        return "Code Quality"
    return area.strip()


def render(findings, root, goal):
    total = len(findings)

    by_impact_effort = OrderedDict((label, []) for label in IMPACT_EFFORT_ORDER)
    area_counts = OrderedDict()
    for f in findings:
        ie = f.get("Impact/Effort", "").strip()
        by_impact_effort.setdefault(ie, []).append(f)
        area = normalize_area(f.get("Area", ""))
        area_counts[area] = area_counts.get(area, 0) + 1

    lines = []
    lines.append("# inHindsight — Architectural Review")
    lines.append("")
    lines.append(f"- **Project root:** `{root}`")
    lines.append(f"- **User goal:** {goal}")
    lines.append(f"- **Generated:** {date.today().isoformat()}")
    lines.append(f"- **Total findings:** {total}")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    area_breakdown = ", ".join(
        f"{count} {area}" for area, count in area_counts.items()
    )
    lines.append(
        f"This review evaluates `{root}` against the stated goal: "
        f"\"{goal}\". It surfaces **{total} finding(s)** ({area_breakdown}), "
        "ranked below by Impact/Effort so the highest-leverage work is "
        "visible first. Each finding lists the issue, the rationale tied "
        "back to the goal above, and a ready-to-use LLM Action Prompt for "
        "executing the fix."
    )
    lines.append("")

    finding_number = 0
    for ie_label in IMPACT_EFFORT_ORDER:
        group = by_impact_effort.get(ie_label, [])
        if not group:
            continue
        lines.append(f"## {IMPACT_EFFORT_LABELS[ie_label]}")
        lines.append("")

        by_area = OrderedDict()
        for f in group:
            by_area.setdefault(normalize_area(f.get("Area", "")), []).append(f)

        ordered_areas = [a for a in AREA_ORDER if a in by_area]
        ordered_areas += [a for a in by_area if a not in AREA_ORDER]

        for area in ordered_areas:
            lines.append(f"### {area}")
            lines.append("")
            for f in by_area[area]:
                finding_number += 1
                lines.append(f"#### {finding_number}. {heading_text(f.get('Issue', ''))}")
                lines.append("")
                lines.append(f"- **Issue:** {f.get('Issue', '')}")
                lines.append(f"- **Rationale:** {f.get('Rationale', '')}")
                lines.append(f"- **Impact/Effort:** {ie_label}")
                lines.append("")
                lines.append("### LLM Action Prompt")
                lines.append("")
                lines.append("```text")
                lines.append(f.get("LLM_Prompt", ""))
                lines.append("```")
                lines.append("")

    # Any Impact/Effort values outside the four canonical labels still get
    # rendered rather than silently dropped, per T4's "don't fabricate,
    # don't discard" convention.
    leftover_labels = [k for k in by_impact_effort if k not in IMPACT_EFFORT_ORDER]
    for ie_label in leftover_labels:
        group = by_impact_effort[ie_label]
        if not group:
            continue
        lines.append(f"## {ie_label or 'Unranked'}")
        lines.append("")
        for f in group:
            finding_number += 1
            lines.append(f"#### {finding_number}. {heading_text(f.get('Issue', ''))}")
            lines.append("")
            lines.append(f"- **Area:** {f.get('Area', '')}")
            lines.append(f"- **Issue:** {f.get('Issue', '')}")
            lines.append(f"- **Rationale:** {f.get('Rationale', '')}")
            lines.append("")
            lines.append("### LLM Action Prompt")
            lines.append("")
            lines.append("```text")
            lines.append(f.get("LLM_Prompt", ""))
            lines.append("```")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("findings_file", nargs="?")
    parser.add_argument("--root", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()

    if args.findings_file:
        with open(args.findings_file, "r", encoding="utf-8") as fh:
            raw = fh.read()
    else:
        if sys.stdin.isatty():
            print("Error: no input file given and stdin is a terminal.", file=sys.stderr)
            return 1
        raw = sys.stdin.read()

    if not raw.strip():
        print("Error: no input findings provided.", file=sys.stderr)
        return 1

    try:
        findings = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error: input is not valid JSON: {e}", file=sys.stderr)
        return 1

    if not isinstance(findings, list) or not findings:
        print("Error: input JSON must be a non-empty array of findings.", file=sys.stderr)
        return 1

    out_path = args.out or f"{args.root.rstrip('/')}/inHindsight.md"
    rendered = render(findings, args.root, args.goal)

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(rendered)

    print(rendered)
    print(f"Wrote {len(findings)} finding(s) to {out_path}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
