#!/usr/bin/env python3
"""Grades Hindsight reviews of an eval fixture, deterministically.

Usage:
    tests/eval/grade.py --expected tests/eval/fixtures/orders-svc.expected.json \
        run1/inHindsight.json [run2/inHindsight.json ...] [--min-recall 0.75] [--json]

For each review it reports:
  - recall: a planted issue counts as found when a finding's evidence
    cites one of its locations (same file; a cited line, if any, within
    `line_tolerance` lines of the planted range). Findings and planted
    issues are matched one-to-one, best match first (a cited line inside
    the range beats one within tolerance, which beats a file-only
    citation; a matching area breaks ties), so one finding can't account
    for two planted issues;
  - leaks: any `forbidden_anywhere` string in the review, or any
    `forbidden_in_prompts` string in a finding's prompt or done_when (the
    text a user pastes into another agent);
  - area coverage: each area has a finding or a no_findings entry;
  - unverified evidence: entries the renderer marked `evidence_unverified`.
Across reviews it reports agreement: for each planted issue, how many
reviews found it and which Impact/Effort buckets they put it in.

Exit codes:
    0  every review meets --min-recall (default: the expected file's) and
       nothing leaked
    1  a leak, a review below the recall bar, or unreadable input
"""

import argparse
import json
import re
import sys

AREAS = ["Architectural Patterns", "Code Quality", "Documentation Gaps"]
LINE_REF = re.compile(r"^(?P<path>.+?):(?P<start>\d+)(?:-(?P<end>\d+))?$")


def clean(path):
    path = path.strip()
    while path.startswith("./"):
        path = path[2:]
    return path


def cited(entry):
    """(path, start, end) for an evidence entry; start/end may be None."""
    if isinstance(entry, dict):
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", str(entry.get("line", "")).strip())
        start = int(m.group(1)) if m else None
        end = int(m.group(2)) if m and m.group(2) else start
        return clean(str(entry.get("path", ""))), start, end
    text = str(entry).strip().split()[0] if str(entry).strip() else ""
    m = LINE_REF.match(text)
    if m:
        start = int(m.group("start"))
        return clean(m.group("path")), start, int(m.group("end") or start)
    return clean(text), None, None


def hit_score(entry, location, tolerance):
    """2 = cited line inside the planted range, 1 = within tolerance,
    0.5 = same file with no line, 0 = no match."""
    path, start, end = cited(entry)
    if not path or not (path == location["file"] or path.endswith("/" + location["file"])):
        return 0
    if start is None:
        return 0.5
    lo, hi = location["lines"]
    if start <= hi and end >= lo:
        return 2
    return 1 if start <= hi + tolerance and end >= lo - tolerance else 0


def match(findings, planted, tolerance):
    """One-to-one assignment of findings to planted issues, best score
    first; ties go to the earlier issue, then the earlier finding."""
    scored = []
    for i, issue in enumerate(planted):
        for j, f in enumerate(findings):
            score = max((hit_score(e, loc, tolerance) for e in f.get("evidence", []) for loc in issue["locations"]),
                        default=0)
            if score:
                scored.append((-(score + (0.25 if f.get("area") == issue["area"] else 0)), i, j))
    taken_issues, taken_findings, pairs = set(), set(), {}
    for _, i, j in sorted(scored):
        if i not in taken_issues and j not in taken_findings:
            taken_issues.add(i)
            taken_findings.add(j)
            pairs[i] = j
    return pairs


def grade_review(review, expected):
    tolerance = expected.get("line_tolerance", 3)
    findings = [f for f in review.get("findings", []) if isinstance(f, dict)]
    found = {}
    for i, j in match(findings, expected["planted"], tolerance).items():
        f = findings[j]
        found[expected["planted"][i]["key"]] = {"id": f.get("id"), "area": f.get("area"),
                                                "bucket": f"{f.get('impact')}/{f.get('effort')}"}

    text = json.dumps(review, ensure_ascii=False)
    leaks = [f"anywhere: {s!r}" for s in expected.get("forbidden_anywhere", []) if s in text]
    for f in findings:
        pasted = f"{f.get('prompt', '')}\n{f.get('done_when', '')}"
        leaks += [f"{f.get('id')} prompt: {s!r}" for s in expected.get("forbidden_in_prompts", []) if s in pasted]

    addressed = {f.get("area") for f in findings} | {e.get("area") for e in review.get("no_findings", [])
                                                      if isinstance(e, dict)}
    return {
        "status": review.get("status"),
        "findings": len(findings),
        "found": found,
        "recall": len(found) / len(expected["planted"]) if expected["planted"] else 1.0,
        "leaks": leaks,
        "unaddressed_areas": [a for a in AREAS if a not in addressed],
        "unverified_evidence": sum(len(f.get("evidence_unverified", [])) for f in findings),
    }


def report(results, expected, min_recall):
    lines = []
    for path, r in results:
        lines.append(f"{path}: status={r['status']} findings={r['findings']} recall={r['recall']:.2f} "
                     f"leaks={len(r['leaks'])} unverified_evidence={r['unverified_evidence']} "
                     f"unaddressed_areas={','.join(r['unaddressed_areas']) or '-'}")
        for leak in r["leaks"]:
            lines.append(f"  LEAK {leak}")
    lines.append("")
    lines.append(f"Agreement across {len(results)} review(s):")
    for issue in expected["planted"]:
        runs = [r["found"].get(issue["key"]) for _, r in results]
        buckets = sorted({h["bucket"] for h in runs if h})
        lines.append(f"  {issue['key']:28} found {sum(1 for h in runs if h)}/{len(runs)}"
                     f"  buckets: {', '.join(buckets) or '-'}")
    lines.append("")
    lines.append(f"Recall bar: {min_recall:.2f}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", required=True)
    parser.add_argument("--min-recall", type=float)
    parser.add_argument("--json", action="store_true", help="print results as JSON")
    parser.add_argument("reviews", nargs="+")
    args = parser.parse_args()

    try:
        with open(args.expected, "r", encoding="utf-8") as fh:
            expected = json.load(fh)
        results = []
        for path in args.reviews:
            with open(path, "r", encoding="utf-8") as fh:
                results.append((path, grade_review(json.load(fh), expected)))
    except (OSError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    min_recall = args.min_recall if args.min_recall is not None else expected.get("min_recall", 0.0)
    if args.json:
        print(json.dumps({"min_recall": min_recall, "results": dict(results)}, indent=2, ensure_ascii=False))
    else:
        print(report(results, expected, min_recall))
    failed = any(r["leaks"] or r["recall"] < min_recall or r["status"] != "complete" for _, r in results)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
