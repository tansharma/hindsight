#!/usr/bin/env python3
"""Roll up Hindsight reviews across several projects into one Markdown page.
No LLM, no network: it only reads what render_output.py already wrote.

Usage:
    scripts/rollup.py --roots <root> [<root> ...] [--out rollup.md]
                      [--stale-days 60] [--today YYYY-MM-DD]

For each root it reads <root>/inHindsight.json and every
<root>/hindsight-history/*.json, keeps the complete reviews (needs-input
runs are noted, not counted), orders them by date, and writes one section
per project:

- a one-row table for the latest complete review: health score (the
  Dependency Health Scorecard's computed score, "n/a" without one), open,
  resolved and won't-fix counts, review date, and age in days;
- a trend line across every complete review: date, health score and open
  count each time, plus the change from first to last.

Open = the latest review's findings, minus those marked resolved or
wontfix with set_status.py (partial stays open). Resolved = distinct
finding ids ever classified resolved in a since_last_review, plus ids
marked resolved by hand in the latest review. Won't fix = findings marked
wontfix in the latest review.

A review is stale when it is more than --stale-days (default 60) days old
on --today (default: the current date); stale reviews are flagged in the
table, under the project, and in the page header. A review's date is its
"generated" field, else the archive filename's date prefix, else the
file's modification date.

Missing roots, missing or unreadable files, and malformed documents are
noted under their project and never stop the run.

Writes to --out, or stdout when it is omitted; a one-line summary goes to
stderr.

Exit codes:
    0  rollup written
    1  bad arguments (an invalid --today or --stale-days), or --out could
       not be written
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime

HISTORY_DIR = "hindsight-history"
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def parse_day(value):
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def review_files(root):
    """(path, label) for every review file under root: history in name
    order, then the current inHindsight.json."""
    files = []
    history = os.path.join(root, HISTORY_DIR)
    if os.path.isdir(history):
        for name in sorted(os.listdir(history)):
            if name.endswith(".json"):
                files.append((os.path.join(history, name), f"{HISTORY_DIR}/{name}"))
    current = os.path.join(root, "inHindsight.json")
    if os.path.isfile(current):
        files.append((current, "inHindsight.json"))
    return files


def review_date(doc, path):
    day = parse_day(doc.get("generated"))
    if day:
        return day
    m = DATE_PREFIX.match(os.path.basename(path))
    if m and parse_day(m.group(1)):
        return parse_day(m.group(1))
    return date.fromtimestamp(os.path.getmtime(path))


def health_score(doc):
    sc = doc.get("dependency_scorecard")
    score = sc.get("health_score") if isinstance(sc, dict) else None
    return score if isinstance(score, (int, float)) and not isinstance(score, bool) else None


def finding_list(doc):
    return [f for f in doc.get("findings") or [] if isinstance(f, dict)]


def open_count(doc):
    return sum(1 for f in finding_list(doc) if f.get("status") not in ("resolved", "wontfix"))


def load_project(root):
    """Everything the page needs for one root."""
    project = {"root": root, "name": os.path.basename(os.path.normpath(root)) or root,
               "reviews": [], "notes": []}
    if not os.path.isdir(root):
        project["notes"].append("Root is not a directory; nothing to read.")
        return project
    needs_input = None
    for path, label in review_files(root):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError) as e:
            project["notes"].append(f"Skipped `{label}`: {e.__class__.__name__}.")
            continue
        if not isinstance(doc, dict):
            project["notes"].append(f"Skipped `{label}`: not a review document.")
            continue
        status = doc.get("status", "complete")
        if status == "needs_input":
            if label == "inHindsight.json":
                needs_input = doc
            continue
        if status != "complete" or not isinstance(doc.get("findings"), list):
            project["notes"].append(f"Skipped `{label}`: not a complete review.")
            continue
        project["reviews"].append({"doc": doc, "date": review_date(doc, path), "label": label})
    project["reviews"].sort(key=lambda r: r["date"])  # stable: name order breaks ties
    if project["reviews"] and isinstance(project["reviews"][-1]["doc"].get("project"), str):
        project["name"] = project["reviews"][-1]["doc"]["project"].strip() or project["name"]
    if needs_input is not None:
        missing = ", ".join(str(m) for m in needs_input.get("missing") or []) or "input"
        project["notes"].append(f"The latest run stopped for input (missing: {missing}); "
                                "figures are from the last complete review.")
    if not project["reviews"] and not project["notes"]:
        project["notes"].append("No review found (no `inHindsight.json` or `hindsight-history/`).")
    return project


def summarize(project, today, stale_days):
    reviews = project["reviews"]
    if not reviews:
        return None
    latest = reviews[-1]
    doc = latest["doc"]
    resolved = set()
    for r in reviews:
        for e in r["doc"].get("since_last_review") or []:
            if isinstance(e, dict) and str(e.get("status", "")).strip().lower() == "resolved" and e.get("id"):
                resolved.add(str(e["id"]).strip())
    resolved |= {f["id"] for f in finding_list(doc) if f.get("status") == "resolved" and f.get("id")}
    age = (today - latest["date"]).days
    return {
        "score": health_score(doc),
        "open": open_count(doc),
        "resolved": len(resolved),
        "wontfix": sum(1 for f in finding_list(doc) if f.get("status") == "wontfix"),
        "date": latest["date"],
        "age": age,
        "stale": age > stale_days,
    }


def pct(score):
    return "n/a" if score is None else f"{score:g}%"


def signed(n, unit):
    return f"{'+' if n > 0 else '−' if n < 0 else '±'}{abs(n):g}{unit}"


def trend_line(reviews):
    points = [f"{r['date'].isoformat()} {pct(health_score(r['doc']))} · {open_count(r['doc'])} open"
              for r in reviews]
    line = " → ".join(points)
    if len(reviews) < 2:
        return f"{line} (one review; no trend yet)"
    first, last = reviews[0]["doc"], reviews[-1]["doc"]
    changes = []
    if health_score(first) is not None and health_score(last) is not None:
        changes.append(f"health {signed(health_score(last) - health_score(first), ' pts')}")
    changes.append(f"open {signed(open_count(last) - open_count(first), '')}")
    return f"{line} ({', '.join(changes)} over {len(reviews)} reviews)"


def cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def render(projects, today, stale_days):
    summaries = [summarize(p, today, stale_days) for p in projects]
    stale = [(p, s) for p, s in zip(projects, summaries) if s and s["stale"]]
    lines = ["# Hindsight Rollup", ""]
    lines.append(f"- **Generated:** {today.isoformat()}")
    lines.append(f"- **Projects:** {len(projects)}")
    if stale:
        lines.append(f"- **⚠️ Stale (over {stale_days} days):** " +
                     ", ".join(f"{p['name']} ({s['age']} days)" for p, s in stale))
    else:
        lines.append(f"- **Stale (over {stale_days} days):** none")
    lines.append("")
    for project, s in zip(projects, summaries):
        lines += [f"## {project['name']}", "", f"`{project['root']}`", ""]
        if s:
            age = f"{s['age']} ⚠️ stale" if s["stale"] else str(s["age"])
            lines += [
                "| Health score | Open | Resolved | Won't fix | Reviewed | Age (days) |",
                "|---|---|---|---|---|---|",
                "| " + " | ".join(cell(v) for v in (pct(s["score"]), s["open"], s["resolved"], s["wontfix"],
                                                    s["date"].isoformat(), age)) + " |",
                "",
                f"**Trend:** {trend_line(project['reviews'])}",
                "",
            ]
            if s["stale"]:
                lines += [f"> ⚠️ The latest complete review is {s['age']} days old (more than {stale_days} days): "
                          "re-run Hindsight on this project.", ""]
        for note in project["notes"]:
            lines.append(f"- {note}")
        if project["notes"]:
            lines.append("")
    return "\n".join(lines).rstrip() + "\n", stale


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--roots", nargs="+", required=True)
    parser.add_argument("--out")
    parser.add_argument("--stale-days", type=int, default=60)
    parser.add_argument("--today", help="YYYY-MM-DD; default: the current date")
    args = parser.parse_args()

    today = parse_day(args.today) if args.today else date.today()
    if today is None:
        print(f"Error: --today '{args.today}' is not a YYYY-MM-DD date.", file=sys.stderr)
        return 1
    if args.stale_days < 0:
        print("Error: --stale-days must be zero or more.", file=sys.stderr)
        return 1

    projects = [load_project(root) for root in args.roots]
    text, stale = render(projects, today, args.stale_days)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as e:
            print(f"Error: could not write --out '{args.out}': {e}", file=sys.stderr)
            return 1
    else:
        sys.stdout.write(text)
    flagged = ", ".join(f"{p['name']} ({s['age']} days)" for p, s in stale) or "none"
    print(f"Rolled up {len(projects)} project(s)" + (f" to {args.out}" if args.out else "") +
          f"; stale reviews: {flagged}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
