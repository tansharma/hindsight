#!/usr/bin/env python3
"""Export the current review's open findings as tasks. No LLM, no network.

Usage:
    scripts/export_tasks.py --root <path> --format markdown --target pending.md
    scripts/export_tasks.py --root <path> --format gh > issues.sh

Open findings are those in <root>/inHindsight.json not marked resolved or
wontfix with set_status.py (partial stays open), in review order.

markdown: keeps a `## Hindsight` section in --target (created, with the
file if needed, at the end). Each finding is one task between
`<!-- hindsight:begin H-NNN -->` and `<!-- hindsight:end H-NNN -->`
markers: a checkbox line with the id, title, rank and area, then the
finding's prompt with its done_when appended, in a fenced block. Tasks are
keyed by id: an existing task is rewritten in place, never duplicated, and
new ones are appended to the section. A task's checkbox keeps whatever the
user set; a task whose finding is no longer open is ticked and labelled
closed, not deleted. Everything outside the markers (other sections, notes
inside this one) is left as it was. The file is written only if its text
changes, so a second export of the same review leaves it byte-identical.

gh: prints one `gh issue create` command per open finding to stdout and
runs nothing. Finding text is treated as data: the title is passed as a
single-quoted shell word (shlex.quote) and the body on stdin through a
quoted heredoc (`--body-file -`, `<<'DELIM'`), whose delimiter is chosen so
that no body line equals it; the shell expands neither. Review the
commands, then run them yourself.

Exit codes:
    0  tasks written (or already current) / commands printed
    1  no review at --root, a needs-input or unreadable document, or the
       target could not be read or written
    2  bad arguments (argparse; --format markdown needs --target)
"""

import argparse
import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from findings_schema import NEEDS_INPUT, rank_label  # noqa: E402
from render_output import code_fence, copyable_prompt  # noqa: E402

SECTION = "## Hindsight"
SECTION_NOTE = ("<!-- Managed by Hindsight's export_tasks.py: tasks between hindsight:begin/end "
                "markers are rewritten on each export; anything else here is kept. -->")
BEGIN = re.compile(r"^<!-- hindsight:begin (H-\d{3,}) -->$")
END = "<!-- hindsight:end {} -->"
CHECKBOX = re.compile(r"^- \[([ xX])\] ")
CLOSED_SUFFIX = re.compile(r" — closed: [^—]*$")
FENCE = re.compile(r"^(```|~~~)")
HEADING = re.compile(r"^#{1,2}\s")


def one_line(text):
    return " ".join(str(text).split())


def load_review(root):
    path = os.path.join(root, "inHindsight.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except OSError:
        raise SystemExit(f"Error: no review found at {path}; run a review first.")
    except ValueError as e:
        raise SystemExit(f"Error: {path} is not valid JSON: {e}")
    if not isinstance(doc, dict) or doc.get("status") == NEEDS_INPUT or not isinstance(doc.get("findings"), list):
        raise SystemExit(f"Error: {path} is not a completed review, so it has no findings to export.")
    findings = [f for f in doc["findings"]
                if isinstance(f, dict) and f.get("id") and f.get("prompt") and f.get("done_when")]
    return doc, findings


def is_open(f):
    return f.get("status") not in ("resolved", "wontfix")


def rank(f):
    if f.get("impact") and f.get("effort"):
        return rank_label(f["impact"], f["effort"])
    return one_line(f.get("rank_label") or "Unranked")


# --- markdown -----------------------------------------------------------------

def task_header(f, box):
    return f"- [{box}] **{f['id']}** {one_line(f.get('title') or f['id'])} _({rank(f)} · {one_line(f.get('area', ''))})_"


def task_block(f, box=" "):
    body = copyable_prompt(f)
    fence = code_fence(body)
    lines = [f"<!-- hindsight:begin {f['id']} -->", task_header(f, box), ""]
    lines.append(f"  {fence}text")
    lines += [f"  {line}" if line else "" for line in body.splitlines()]
    lines.append(f"  {fence}")
    lines.append(END.format(f["id"]))
    return lines


def close_block(block, reason):
    """Tick a task whose finding is no longer open and label why."""
    out = list(block)
    header = out[1] if len(out) > 1 else ""
    if CHECKBOX.match(header):
        header = CLOSED_SUFFIX.sub("", "- [x] " + header[6:]) + f" — closed: {reason}"
        out[1] = header
    return out


def find_section(lines):
    """(start, end) of the Hindsight section: the heading's index and the
    index of the next level-1/2 heading outside a fence (or len)."""
    start = next((i for i, l in enumerate(lines) if l.rstrip() == SECTION), None)
    if start is None:
        return None, None
    in_fence = False
    for i in range(start + 1, len(lines)):
        if FENCE.match(lines[i]):
            in_fence = not in_fence
        elif not in_fence and HEADING.match(lines[i]):
            return start, i
    return start, len(lines)


def parse_section(body):
    """Split the section body into items: ("text", line) or
    ("task", id, [lines]). An unterminated begin marker is kept as text."""
    items, i = [], 0
    while i < len(body):
        m = BEGIN.match(body[i])
        if m:
            end = END.format(m.group(1))
            j = next((k for k in range(i + 1, len(body)) if body[k] == end), None)
            if j is not None:
                items.append(("task", m.group(1), body[i:j + 1]))
                i = j + 1
                continue
        items.append(("text", body[i]))
        i += 1
    return items


def update_markdown(text, findings):
    """Return the new file text with the Hindsight section brought up to date."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    start, end = find_section(lines)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines += [SECTION, "", SECTION_NOTE, ""]
        start, end = find_section(lines)

    body = lines[start + 1:end]
    items = parse_section(body)
    by_id = {f["id"]: f for f in findings}
    open_ids = [f["id"] for f in findings if is_open(f)]
    seen = set()
    new_items = []
    for item in items:
        if item[0] != "task":
            new_items.append(item)
            continue
        _, fid, block = item
        if fid in seen:
            continue  # a duplicate left by hand: keep the first only
        seen.add(fid)
        f = by_id.get(fid)
        if f is not None and is_open(f):
            m = CHECKBOX.match(block[1]) if len(block) > 1 else None
            box = m.group(1) if m else " "
            new_items.append(("task", fid, task_block(f, "x" if box in "xX" else " ")))
        else:
            reason = f"marked {f['status']}" if f is not None else "not in the latest review"
            new_items.append(("task", fid, close_block(block, reason)))

    # Append tasks for newly open findings after the last task (or at the
    # end of the section, before its trailing blank lines).
    additions = []
    for fid in open_ids:
        if fid not in seen:
            additions += task_block(by_id[fid]) + [""]
    if additions:
        last_task = max((n for n, it in enumerate(new_items) if it[0] == "task"), default=None)
        if last_task is None:
            insert_at = len(new_items)
            while insert_at > 0 and new_items[insert_at - 1] == ("text", ""):
                insert_at -= 1
            prefix = [("text", "")] if insert_at and new_items[insert_at - 1] != ("text", "") else []
        else:
            insert_at = last_task + 1
            prefix = [("text", "")]
            if insert_at < len(new_items) and new_items[insert_at] == ("text", ""):
                insert_at += 1
                prefix = []
        added = prefix + [("text", l) for l in additions[:-1]]
        if insert_at < len(new_items) and new_items[insert_at] != ("text", ""):
            added.append(("text", ""))
        new_items[insert_at:insert_at] = added

    new_body = []
    for item in new_items:
        new_body += [item[1]] if item[0] == "text" else item[2]
    if end < len(lines) and (not new_body or new_body[-1].strip()):
        new_body.append("")
    result = lines[:start + 1] + new_body + lines[end:]
    while result and result[-1] == "":
        result.pop()
    return "\n".join(result) + "\n"


def export_markdown(target, findings):
    try:
        with open(target, "r", encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        text = ""
    except OSError as e:
        raise SystemExit(f"Error: could not read --target '{target}': {e}")
    updated = update_markdown(text, findings)
    open_count = sum(1 for f in findings if is_open(f))
    if updated == text:
        print(f"{target} already lists the {open_count} open finding(s); unchanged.", file=sys.stderr)
        return
    try:
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(updated)
    except OSError as e:
        raise SystemExit(f"Error: could not write --target '{target}': {e}")
    print(f"Wrote {open_count} open finding(s) to {target}.", file=sys.stderr)


# --- gh -----------------------------------------------------------------------

def issue_body(f, doc):
    lines = [f"**Issue:** {f.get('issue', '')}", "", f"**Rationale:** {f.get('rationale', '')}", ""]
    lines.append(f"**Impact/Effort:** {rank(f)} · **Area:** {one_line(f.get('area', ''))}")
    evidence = []
    for e in f.get("evidence") or []:
        if isinstance(e, dict):
            evidence.append(f"{e.get('path', '')}:{e['line']}" if e.get("line") else str(e.get("path", "")))
        else:
            evidence.append(str(e))
    if evidence:
        lines.append(f"**Evidence:** {', '.join(evidence)}")
    body = copyable_prompt(f)
    fence = code_fence(body)
    lines += ["", "**LLM Action Prompt**", "", f"{fence}text", body, fence, ""]
    by = f", Hindsight {doc['hindsight_version']}" if doc.get("hindsight_version") else ""
    lines.append(f"_From Hindsight finding {f['id']} (review of {doc.get('generated', 'unknown date')}{by})._")
    return "\n".join(lines)


def heredoc_delimiter(fid, body):
    base = f"HINDSIGHT_{fid.replace('-', '_')}_BODY"
    taken = set(body.split("\n"))
    delim, n = base, 1
    while delim in taken:
        delim, n = f"{base}_{n}", n + 1
    return delim


def gh_commands(doc, findings):
    out = ["#!/usr/bin/env bash",
           "# gh issue commands for the open Hindsight findings, generated by export_tasks.py.",
           "# Nothing has been run. Review these, then run them yourself (e.g. bash issues.sh).",
           "# Titles are single-quoted and bodies are quoted heredocs: the shell expands neither.",
           "set -euo pipefail", ""]
    for f in findings:
        if not is_open(f):
            continue
        title = f"[{f['id']}] {one_line(f.get('title') or f['id'])}"
        body = issue_body(f, doc)
        delim = heredoc_delimiter(f["id"], body)
        out.append(f"gh issue create --title {shlex.quote(title)} --body-file - <<'{delim}'")
        out.append(body)
        out.append(delim)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--format", required=True, choices=["markdown", "gh"])
    parser.add_argument("--target", help="markdown: the file to keep the ## Hindsight section in")
    args = parser.parse_args()
    if args.format == "markdown" and not args.target:
        parser.error("--format markdown needs --target <file>")

    try:
        doc, findings = load_review(args.root)
        if args.format == "markdown":
            export_markdown(args.target, findings)
        else:
            sys.stdout.write(gh_commands(doc, findings))
            n = sum(1 for f in findings if is_open(f))
            print(f"Printed {n} gh issue create command(s); none were run.", file=sys.stderr)
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            return 1
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
