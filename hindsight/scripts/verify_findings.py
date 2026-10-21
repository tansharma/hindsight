"""Checks a normalized findings document's claims against the project on
disk. Imported by render_output.py; not run directly.

Two checks, both reported as warnings (never fatal, never dropping a
finding):

- Evidence. Each evidence entry is either a string ("path", "path:42",
  "path:42-50") or an object {"path", "line", "quote"}. The path must exist
  under the project root and the line (range) must lie within the file. A
  quote must appear verbatim (whitespace-insensitive) within QUOTE_WINDOW
  lines of the cited line, or anywhere in the file when no line is given.
  Strings that are plainly not paths ("README.md — new section" with no
  path-like first token) are skipped.
- Re-run coverage. Against the previous complete review: every previous id
  must appear in since_last_review, every since_last_review id must have
  been a previous finding, and every previous finding marked unresolved or
  partial must be carried forward under its id.
"""

import json
import os
import re

# How far (in lines) a quote may sit from the cited line and still count.
QUOTE_WINDOW = 3

LINE_SUFFIX = re.compile(r"^(?P<path>.+?):(?P<start>\d+)(?:-(?P<end>\d+))?$")

CARRY_FORWARD = ("unresolved", "partial")


def squash(text):
    return " ".join(text.split())


def looks_like_path(token):
    return "/" in token or bool(re.search(r"\.\w+(:\d+(-\d+)?)?$", token))


def parse_evidence(entry):
    """Return (path, start, end, quote, label) for an evidence entry, or None
    if it is plainly not a file reference. start/end are ints or None."""
    if isinstance(entry, dict):
        path = str(entry.get("path", "")).strip()
        line = str(entry.get("line", "")).strip()
        quote = str(entry.get("quote", "")).strip() or None
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", line)
        start = int(m.group(1)) if m else None
        end = int(m.group(2)) if m and m.group(2) else start
        label = f"{path}:{line}" if line else path
        return path, start, end, quote, label

    text = str(entry).strip()
    if any(c.isspace() for c in text):
        first = text.split()[0]
        if not looks_like_path(first):
            return None
        text = first
    m = LINE_SUFFIX.match(text)
    if m:
        start = int(m.group("start"))
        end = int(m.group("end")) if m.group("end") else start
        return m.group("path"), start, end, None, str(entry).strip()
    if not looks_like_path(text):
        return None
    return text, None, None, None, str(entry).strip()


def resolve_under(root, path):
    """Absolute path of `path` (relative to root, or absolute) if it is a
    file inside root, else None."""
    root_real = os.path.realpath(root)
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(root, path))
    if full != root_real and not full.startswith(root_real + os.sep):
        return None
    return full if os.path.isfile(full) else None


def check_evidence_entry(root, entry):
    """Return a problem description for one evidence entry, or None."""
    parsed = parse_evidence(entry)
    if parsed is None:
        return None
    path, start, end, quote, label = parsed
    if not path:
        return f"evidence {label!r} has no path"
    full = resolve_under(root, path)
    if full is None:
        return f"evidence {label!r} not found under root"
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError as e:
        return f"evidence {label!r} unreadable: {e}"
    if start is not None and (start < 1 or end < start or end > len(lines)):
        return f"evidence {label!r} line out of range (file has {len(lines)} lines)"
    if quote:
        wanted = squash(quote)
        if start is not None:
            lo, hi = max(0, start - 1 - QUOTE_WINDOW), min(len(lines), end + QUOTE_WINDOW)
            if wanted in squash(" ".join(lines[lo:hi])):
                return None
        lines_quoted = quote.count("\n") + 1
        # Exact line count first, then allow the excerpt to wrap one more line.
        for span in (lines_quoted, lines_quoted + 1):
            for n in range(len(lines)):
                if wanted in squash(" ".join(lines[n:n + span])):
                    if start is None:
                        return None
                    return f"evidence {label!r} quote found near line {n + 1}, not at the cited line"
        return f"evidence {label!r} quote not found in {path}"
    return None


def verify_evidence(doc, warnings):
    """Warn about unresolvable evidence; record it per finding as
    evidence_unverified (only when non-empty)."""
    root = doc["root"]
    for f in doc["findings"]:
        unverified = []
        for entry in f.get("evidence", []):
            problem = check_evidence_entry(root, entry)
            if problem:
                warnings.append(f"{f['id']}: {problem}")
                unverified.append(entry)
        if unverified:
            f["evidence_unverified"] = unverified
        else:
            f.pop("evidence_unverified", None)


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def previous_review(json_path, history_dir):
    """The previous complete review: the current output if it is one, else
    the newest archived complete review. None if there is none."""
    current = load_json(json_path)
    if current and current.get("status", "complete") == "complete":
        return current
    if not os.path.isdir(history_dir):
        return None
    archived = [os.path.join(history_dir, n) for n in os.listdir(history_dir) if n.endswith(".json")]
    for path in sorted(archived, key=lambda p: (os.path.getmtime(p), p), reverse=True):
        data = load_json(path)
        if data and data.get("status", "complete") == "complete":
            return data
    return None


def verify_rerun_coverage(doc, previous, warnings):
    """Warn where since_last_review doesn't account for the previous review,
    or a finding it calls unresolved/partial was not carried forward."""
    if not previous:
        return
    prev_ids = [f.get("id") for f in previous.get("findings", []) if isinstance(f, dict) and f.get("id")]
    if not prev_ids:
        return
    entries = [e for e in doc.get("since_last_review") or [] if isinstance(e, dict)]
    if not entries:
        warnings.append(
            f"the previous review has {len(prev_ids)} finding(s) but since_last_review is empty "
            "(Step 6); classify each previous finding"
        )
        return
    reviewed = {}
    for e in entries:
        reviewed[str(e.get("id", "")).strip()] = str(e.get("status", "")).strip().lower()
    current_ids = {f["id"] for f in doc["findings"]}
    for pid in prev_ids:
        if pid not in reviewed:
            warnings.append(f"since_last_review does not classify previous finding {pid}")
        elif reviewed[pid].startswith(CARRY_FORWARD) and pid not in current_ids:
            warnings.append(f"{pid} is marked {reviewed[pid]} but was not carried forward under its id")
    for rid in reviewed:
        if rid and rid not in prev_ids:
            warnings.append(f"since_last_review entry {rid} was not a finding in the previous review")
