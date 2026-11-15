#!/usr/bin/env python3
"""Mark one finding of the current review as resolved, partially resolved,
or won't-fix, between reviews.

Usage:
    scripts/set_status.py --root <path> --id H-004 \
        --status resolved|partial|wontfix --note "<why>" [--commit <sha>]

Updates the finding's optional `status`, `status_note` and `status_commit`
fields (findings_schema.py) in <root>/inHindsight.json, then re-renders
<root>/inHindsight.md from that document with render_output.py's renderer.
Nothing is archived, no id changes, and the review's `generated` date is
kept: this edits the current review, it is not a new one. Each call
replaces the finding's previous status entirely (a status set without
--commit drops an earlier commit), so repeating a call changes nothing.

The status is the user's claim, recorded by hand. The next review reads it
as prior evidence and still verifies it against the code (SKILL.md Step 6).

Exit codes:
    0  status recorded (or already identical)
    1  no review at --root, a needs-input or unreadable document, an
       unknown id, or an empty note / malformed commit
    2  bad arguments (argparse)
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from findings_schema import FINDING_STATUSES, ID_PATTERN, NEEDS_INPUT  # noqa: E402
import render_output  # noqa: E402

COMMIT_PATTERN = re.compile(r"[0-9a-fA-F]{4,64}")


def fail(message):
    print(f"Error: {message}", file=sys.stderr)
    return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--status", required=True, choices=FINDING_STATUSES)
    parser.add_argument("--note", required=True)
    parser.add_argument("--commit")
    args = parser.parse_args()

    finding_id = args.id.strip().upper()
    if not ID_PATTERN.fullmatch(finding_id):
        return fail(f"--id '{args.id}' is not a finding id (expected H-NNN).")
    note = " ".join(args.note.split())
    if not note:
        return fail("--note must say why the status is being set.")
    commit = (args.commit or "").strip()
    if args.commit is not None and not COMMIT_PATTERN.fullmatch(commit):
        return fail(f"--commit '{args.commit}' is not a commit hash (4-64 hex digits).")

    json_path = os.path.join(args.root, "inHindsight.json")
    md_path = os.path.join(args.root, "inHindsight.md")
    try:
        with open(json_path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except OSError:
        return fail(f"no review found at {json_path}; run a review first.")
    except ValueError as e:
        return fail(f"{json_path} is not valid JSON: {e}")
    if not isinstance(doc, dict) or doc.get("status") == NEEDS_INPUT or not isinstance(doc.get("findings"), list):
        return fail(f"{json_path} is not a completed review, so it has no findings to mark.")

    matches = [f for f in doc["findings"] if isinstance(f, dict) and f.get("id") == finding_id]
    if not matches:
        known = ", ".join(str(f.get("id")) for f in doc["findings"] if isinstance(f, dict)) or "none"
        return fail(f"no finding {finding_id} in {json_path} (ids: {known}).")
    finding = matches[0]

    before = json.dumps(doc, sort_keys=True)
    finding["status"] = args.status
    finding["status_note"] = note
    if commit:
        finding["status_commit"] = commit
    else:
        finding.pop("status_commit", None)

    try:
        rendered = render_output.render(doc, [])
    except (KeyError, TypeError, AttributeError) as e:
        return fail(f"{json_path} is not a document render_output.py wrote ({e.__class__.__name__}: {e}); "
                    "nothing was changed.")

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(rendered)

    changed = json.dumps(doc, sort_keys=True) != before
    print(f"{finding_id} {'marked' if changed else 'already'} {args.status}; "
          f"updated {json_path} and {md_path}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
