"""The findings contract shared by parse_findings.py and render_output.py.

A findings document is a JSON object:

    {
      "schema_version": 1,
      "project": "<name>",            # optional; defaults to the root's basename
      "root": "<path>",               # optional if passed on the command line
      "goal": "<user goal>",          # optional if passed on the command line
      "summary": "<verdict paragraph>",                     # optional
      "findings": [
        {
          "id": "H-001",              # optional; assigned at render time
          "area": "Architectural Patterns | Code Quality | Documentation Gaps",
          "title": "<short title>",   # optional; defaults to the issue's first line
          "issue": "...",
          "rationale": "...",
          "impact": "High | Low",
          "effort": "High | Low",
          "evidence": ["path/to/file.py:42", ...],          # optional
          "prompt": "<self-contained LLM action prompt>",
          "done_when": "<how to verify the fix>",
          "decision_matrix": [ {solution, impact, effort, argument}, ... ]
                                      # optional; at most one finding per review
        }
      ],
      "gap_report": [ {"element", "type", "location"}, ... ],  # optional
      "since_last_review": [ {"id", "title", "status", "evidence"}, ... ]
                                      # optional; status is resolved | partial |
                                      # unresolved | obsolete
    }

A bare array of findings is accepted as a document with only "findings".
The pre-JSON keys (Area, Issue, Rationale, Impact/Effort, LLM_Prompt,
Done_When) are accepted too, so prose parsed by parse_findings.py and older
saved findings still load.
"""

import re

SCHEMA_VERSION = 1

AREA_ORDER = ["Architectural Patterns", "Code Quality", "Documentation Gaps"]

# Priority order: quick wins first, then strategic bets, then easy cleanup,
# then lowest priority. Matches project.md's Impact/Effort decision matrix.
IMPACT_EFFORT_ORDER = [("High", "Low"), ("High", "High"), ("Low", "Low"), ("Low", "High")]

REVIEW_STATUSES = ["resolved", "partial", "unresolved", "obsolete"]

LEGACY_KEYS = {
    "Area": "area",
    "Issue": "issue",
    "Rationale": "rationale",
    "Impact/Effort": "impact_effort",
    "LLM_Prompt": "prompt",
    "Done_When": "done_when",
}

REQUIRED_TEXT = ["area", "issue", "rationale", "prompt", "done_when"]

ID_PATTERN = re.compile(r"H-(\d{3,})")

HEADING_MAX_LEN = 90

# "High impact / low effort (quick win)", "high-impact, low-effort", and
# "Impact: High / Effort: Low" all name a canonical bucket.
IMPACT_FIRST = re.compile(r"\b(high|low)[\s-]*impact\b.*?\b(high|low)[\s-]*effort\b", re.I | re.S)
LABEL_FIRST = re.compile(r"\bimpact\W*(high|low)\b.*?\beffort\W*(high|low)\b", re.I | re.S)


def rank_label(impact, effort):
    return f"{impact} Impact / {effort} Effort"


def canonical_impact_effort(value):
    """Return (impact, effort) for a free-text label, or None if it names no bucket."""
    for pattern in (IMPACT_FIRST, LABEL_FIRST):
        m = pattern.search(value)
        if m:
            return m.group(1).capitalize(), m.group(2).capitalize()
    return None


def level(value):
    if isinstance(value, str) and value.strip().capitalize() in ("High", "Low"):
        return value.strip().capitalize()
    return None


def normalize_area(area):
    lowered = area.lower()
    if "architect" in lowered:
        return "Architectural Patterns"
    if "doc" in lowered:
        return "Documentation Gaps"
    if "code" in lowered or "quality" in lowered:
        return "Code Quality"
    return area.strip()


def heading_text(text):
    first_line = text.splitlines()[0] if text else ""
    if len(first_line) <= HEADING_MAX_LEN:
        return first_line
    cut = first_line[:HEADING_MAX_LEN].rsplit(" ", 1)[0]
    return f"{cut}…"


def text_field(f, key):
    value = f.get(key)
    return value.strip() if isinstance(value, str) else ""


def normalize_finding(raw):
    """Return (finding, problem). finding is None when it is unusable."""
    if not isinstance(raw, dict):
        return None, "not a JSON object"
    f = {LEGACY_KEYS.get(k, k): v for k, v in raw.items()}

    missing = [k for k in REQUIRED_TEXT if not text_field(f, k)]
    impact, effort = level(f.get("impact")), level(f.get("effort"))
    raw_rank = text_field(f, "impact_effort")
    if not (impact and effort) and not raw_rank and (f.get("impact") or f.get("effort")):
        raw_rank = rank_label(str(f.get("impact") or "?").strip(), str(f.get("effort") or "?").strip())
    if not (impact and effort) and raw_rank:
        impact, effort = canonical_impact_effort(raw_rank) or (None, None)
    if not (impact and effort) and not raw_rank:
        missing.append("impact/effort")
    if missing:
        return None, "missing " + ", ".join(missing)

    out = {}
    if isinstance(f.get("id"), str) and ID_PATTERN.fullmatch(f["id"].strip()):
        out["id"] = f["id"].strip()
    out["area"] = normalize_area(text_field(f, "area"))
    out["title"] = text_field(f, "title") or heading_text(text_field(f, "issue"))
    for key in ("issue", "rationale"):
        out[key] = text_field(f, key)
    out["impact"], out["effort"] = impact, effort
    if not (impact and effort):
        # Off-spec labels still render (in their own section) rather than
        # being silently discarded.
        out["rank_label"] = raw_rank
    evidence = f.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    out["evidence"] = [str(e).strip() for e in evidence if str(e).strip()]
    out["prompt"] = text_field(f, "prompt")
    out["done_when"] = text_field(f, "done_when")
    if f.get("decision_matrix"):
        out["decision_matrix"] = f["decision_matrix"]
    return out, None


def normalize_document(data):
    """Accept a findings document or a bare findings array.

    Returns (doc, warnings); doc["findings"] holds only usable findings.
    Raises ValueError if data has no findings list at all.
    """
    if isinstance(data, list):
        data = {"findings": data}
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        raise ValueError('expected a findings document {"findings": [...]} or an array of findings')

    doc = {k: v for k, v in data.items() if k != "findings"}
    doc["schema_version"] = SCHEMA_VERSION
    doc["findings"] = []
    warnings = []
    for i, raw in enumerate(data["findings"], 1):
        finding, problem = normalize_finding(raw)
        if finding is None:
            warnings.append(f"dropped finding {i}: {problem}")
        else:
            doc["findings"].append(finding)
    return doc, warnings


def id_number(finding_id):
    m = ID_PATTERN.fullmatch(finding_id or "")
    return int(m.group(1)) if m else 0


def assign_ids(findings, reserved=()):
    """Give every finding a unique H-NNN id, keeping valid existing ones.

    New ids are numbered after the highest id in `findings` and `reserved`
    (the previous run's ids), so a number is never reused for a different
    finding across runs. Returns warnings for duplicate ids that were replaced.
    """
    next_n = max([id_number(f.get("id")) for f in findings] + [id_number(r) for r in reserved] + [0]) + 1
    seen = set()
    warnings = []
    for f in findings:
        if f.get("id") in seen:
            warnings.append(f"duplicate id {f['id']} reassigned")
            f.pop("id")
        if not f.get("id"):
            f["id"] = f"H-{next_n:03d}"
            next_n += 1
        seen.add(f["id"])
    return warnings
