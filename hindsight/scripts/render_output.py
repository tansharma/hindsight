#!/usr/bin/env python3
"""T5 test script: renders a findings document (the contract in
findings_schema.py — typically written by the agent, or produced by
scripts/parse_findings.py) into the final deliverables.

Usage:
    scripts/parse_findings.py review.txt | \
      scripts/render_output.py --root <path> --goal "<use case>"
    # or
    scripts/render_output.py [--root <path>] [--goal "<use case>"] findings.json

Input is a findings document or a bare array of findings. --root and --goal
override the document's own "root"/"goal"; one of the two must supply each.

Writes:
    <root>/inHindsight.md     (or --out)        the human-readable review
    <root>/inHindsight.json   (or --json-out)   the normalized document, with ids
If either file already exists, both existing files are first moved to
<dir of --out>/hindsight-history/<timestamp>-<name>, so no run is lost. New
finding ids are numbered after the previous run's highest id and never reuse
a number; findings carried forward should keep their old id in the input.

This step is rendering, not analysis or re-judging — every usable finding in
the input appears in the output exactly once, grouped and formatted, with no
findings added or reworded. The rendered markdown is also printed to stdout.

Exit codes:
    0  inHindsight.md and inHindsight.json written
    1  no input, invalid JSON, no usable findings, missing root/goal, or more
       than one finding carrying a decision_matrix
"""

import argparse
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from findings_schema import (  # noqa: E402
    AREA_ORDER,
    IMPACT_EFFORT_ORDER,
    REVIEW_STATUSES,
    assign_ids,
    normalize_document,
    rank_label,
)
import render_decision_matrix  # noqa: E402

BUCKET_ICONS = {
    ("High", "Low"): "⚡",
    ("High", "High"): "\U0001f3d7️",
    ("Low", "Low"): "\U0001f9f9",
    ("Low", "High"): "\U0001f551",
}

STATUS_LABELS = {
    "resolved": "Resolved",
    "partial": "Partially resolved",
    "unresolved": "Unresolved",
    "obsolete": "Obsolete",
}

HISTORY_DIR = "hindsight-history"


def code_fence(content):
    """A backtick fence longer than any backtick run inside content, so a
    prompt that contains its own ``` block can't close the fence early."""
    longest = max((len(run) for run in re.findall(r"`+", content)), default=0)
    return "`" * max(3, longest + 1)


def prompt_block(prompt):
    fence = code_fence(prompt)
    return [f"{fence}text", prompt, fence]


def table_cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def copyable_prompt(f):
    """The prompt the user pastes: the finding's prompt plus its acceptance
    criteria, so the receiving agent knows when it is done."""
    return f"{f['prompt']}\n\nDone when:\n{f['done_when']}"


def render_matrix(f, warnings):
    candidates = f.get("decision_matrix")
    if not isinstance(candidates, list):
        warnings.append(f"{f['id']}: decision_matrix is not an array; skipped")
        return []
    kept = [c for c in candidates if render_decision_matrix.valid_candidate(c)]
    if len(kept) < render_decision_matrix.MIN_CANDIDATES:
        warnings.append(
            f"{f['id']}: decision_matrix has {len(kept)} valid candidate(s), "
            f"needs {render_decision_matrix.MIN_CANDIDATES}; skipped"
        )
        return []
    return ["**Decision Matrix**", "", render_decision_matrix.render(kept).rstrip(), ""]


def render_finding(f, warnings):
    lines = [f"#### {f['id']}. {f['title']}", ""]
    if f.get("rank_label") is not None:
        lines.append(f"- **Area:** {f['area']}")
    lines.append(f"- **Issue:** {f['issue']}")
    lines.append(f"- **Rationale:** {f['rationale']}")
    if f.get("impact"):
        lines.append(f"- **Impact/Effort:** {rank_label(f['impact'], f['effort'])}")
    if f["evidence"]:
        lines.append("- **Evidence:** " + ", ".join(f"`{e}`" for e in f["evidence"]))
    lines.append(f"- **Done when:** {f['done_when']}")
    lines.append("")
    lines.append("**LLM Action Prompt**")
    lines.append("")
    lines.extend(prompt_block(copyable_prompt(f)))
    lines.append("")
    if f.get("decision_matrix"):
        lines.extend(render_matrix(f, warnings))
    return lines


def render_since_last_review(items, warnings):
    if not isinstance(items, list) or not items:
        return []
    counts = OrderedDict((s, 0) for s in REVIEW_STATUSES)
    rows = []
    for item in items:
        if not isinstance(item, dict):
            warnings.append("since_last_review entry is not an object; skipped")
            continue
        status = str(item.get("status", "")).strip().lower()
        if status.startswith("partial"):
            status = "partial"
        if status not in counts:
            warnings.append(f"since_last_review {item.get('id', '?')}: unknown status {status!r}; skipped")
            continue
        counts[status] += 1
        label = " ".join(str(item.get(k, "")).strip() for k in ("id", "title")).strip()
        evidence = str(item.get("evidence", "")).strip()
        rows.append(f"- **{label}** — {STATUS_LABELS[status]}" + (f": {evidence}" if evidence else ""))
    if not rows:
        return []
    total = sum(counts.values())
    tally = ", ".join(f"{n} {STATUS_LABELS[s].lower()}" for s, n in counts.items() if n)
    return ["## Since Last Review", "", f"{total} previous finding(s): {tally}.", ""] + rows + [""]


def render_gap_report(entries, warnings):
    if not isinstance(entries, list):
        return []
    rows = []
    for e in entries:
        if not isinstance(e, dict) or not str(e.get("element", "")).strip():
            warnings.append("gap_report entry without an element; skipped")
            continue
        rows.append(f"| {table_cell(e['element'])} | {table_cell(e.get('type', ''))} | {table_cell(e.get('location', ''))} |")
    if not rows:
        return []
    return [
        "## 📋 Cross-Reference Documentation Gap Report",
        "",
        "| Element Name | Type | Suggested Location |",
        "|---|---|---|",
    ] + rows + [""]


def render(doc, warnings=None):
    warnings = [] if warnings is None else warnings
    findings = doc["findings"]
    root, goal = doc["root"], doc["goal"]
    total = len(findings)
    project = doc.get("project") or os.path.basename(os.path.abspath(root)) or root

    area_counts = OrderedDict()
    for f in findings:
        area_counts[f["area"]] = area_counts.get(f["area"], 0) + 1
    area_breakdown = ", ".join(f"{count} {area}" for area, count in area_counts.items())

    lines = [f"# In Hindsight — {project}", ""]
    lines.append(f"- **Project root:** `{root}`")
    lines.append(f"- **User goal:** {goal}")
    lines.append(f"- **Generated:** {doc['generated']}")
    lines.append(f"- **Total findings:** {total}")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    summary = doc.get("summary")
    if isinstance(summary, str) and summary.strip():
        lines.append(summary.strip())
        lines.append("")
        lines.append(f"**{total} finding(s)** ({area_breakdown}), ranked below by Impact/Effort.")
    else:
        lines.append(
            f"This review evaluates `{root}` against the stated goal: "
            f"\"{goal}\". It surfaces **{total} finding(s)** ({area_breakdown}), "
            "ranked below by Impact/Effort so the highest-leverage work is "
            "visible first. Each finding lists the issue, the rationale tied "
            "back to the goal above, how to tell it is done, and a "
            "ready-to-use LLM Action Prompt for executing the fix."
        )
    lines.append("")

    lines.extend(render_since_last_review(doc.get("since_last_review"), warnings))

    for impact, effort in IMPACT_EFFORT_ORDER:
        group = [f for f in findings if (f.get("impact"), f.get("effort")) == (impact, effort)]
        if not group:
            continue
        lines.append(f"## {BUCKET_ICONS[(impact, effort)]} {rank_label(impact, effort)}")
        lines.append("")

        by_area = OrderedDict()
        for f in group:
            by_area.setdefault(f["area"], []).append(f)
        ordered_areas = [a for a in AREA_ORDER if a in by_area]
        ordered_areas += [a for a in by_area if a not in AREA_ORDER]

        for area in ordered_areas:
            lines.append(f"### {area}")
            lines.append("")
            for f in by_area[area]:
                lines.extend(render_finding(f, warnings))

    # Off-spec Impact/Effort labels still get rendered rather than silently
    # dropped, per T4's "don't fabricate, don't discard" convention.
    unranked = OrderedDict()
    for f in findings:
        if f.get("rank_label") is not None:
            unranked.setdefault(f["rank_label"] or "Unranked", []).append(f)
    for label, group in unranked.items():
        lines.append(f"## {label}")
        lines.append("")
        for f in group:
            lines.extend(render_finding(f, warnings))

    lines.extend(render_gap_report(doc.get("gap_report"), warnings))

    return "\n".join(lines).rstrip() + "\n"


def previous_ids(json_path):
    try:
        with open(json_path, "r", encoding="utf-8") as fh:
            prior = json.load(fh)
        return [f.get("id") for f in prior.get("findings", []) if isinstance(f, dict)]
    except (OSError, ValueError, AttributeError):
        return []


def archive_previous(paths, history_dir):
    """Move existing output files into history_dir under one shared
    timestamp prefix (the newest file's mtime). Returns the new paths."""
    existing = [p for p in paths if os.path.exists(p)]
    if not existing:
        return []
    stamp = datetime.fromtimestamp(max(os.path.getmtime(p) for p in existing)).strftime("%Y-%m-%dT%H%M%S")
    os.makedirs(history_dir, exist_ok=True)
    prefix, n = stamp, 1
    while any(os.path.exists(os.path.join(history_dir, f"{prefix}-{os.path.basename(p)}")) for p in existing):
        prefix, n = f"{stamp}-{n}", n + 1
    moved = []
    for p in existing:
        dest = os.path.join(history_dir, f"{prefix}-{os.path.basename(p)}")
        os.replace(p, dest)
        moved.append(dest)
    return moved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("findings_file", nargs="?")
    parser.add_argument("--root")
    parser.add_argument("--goal")
    parser.add_argument("--out")
    parser.add_argument("--json-out")
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
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error: input is not valid JSON: {e}", file=sys.stderr)
        return 1

    try:
        doc, warnings = normalize_document(data)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    for key in ("root", "goal"):
        value = getattr(args, key) or doc.get(key)
        if not isinstance(value, str) or not value.strip():
            print(f"Error: no {key} given (pass --{key} or set \"{key}\" in the document).", file=sys.stderr)
            return 1
        doc[key] = value

    if not doc["findings"]:
        for w in warnings:
            print(f"Warning: {w}", file=sys.stderr)
        print("Error: input contains no usable findings.", file=sys.stderr)
        return 1

    with_matrix = [f for f in doc["findings"] if f.get("decision_matrix")]
    if len(with_matrix) > 1:
        print(
            f"Error: {len(with_matrix)} findings carry a decision_matrix; "
            "only the single most critical finding may have one.",
            file=sys.stderr,
        )
        return 1

    out_path = args.out or os.path.join(doc["root"], "inHindsight.md")
    json_path = args.json_out or os.path.splitext(out_path)[0] + ".json"

    warnings += assign_ids(doc["findings"], previous_ids(json_path))
    doc["generated"] = date.today().isoformat()
    rendered = render(doc, warnings)

    archived = archive_previous([out_path, json_path], os.path.join(os.path.dirname(os.path.abspath(out_path)), HISTORY_DIR))

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(rendered)
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)
    print(rendered)
    for path in archived:
        print(f"Archived previous output to {path}.", file=sys.stderr)
    print(f"Wrote {len(doc['findings'])} finding(s) to {out_path} and {json_path}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
