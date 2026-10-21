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
      "no_findings": [ {"area", "reason"}, ... ],
                                      # optional; an area with nothing worth
                                      # reporting, and why it is clean
      "gap_report": [ {"element", "type", "location"}, ... ],  # optional
      "dependency_scorecard": {       # optional; see SCORE_DEDUCTIONS
        "packages_reviewed": 12,
        "risky_packages": [ {"package", "version", "basis", "evidence",
                             "verified": true | false}, ... ],
        "cycles": [ {"modules": ["a.py", "b.py"], "evidence"}, ... ],
        "volatile_hubs": [ {"module", "fan_in", "signals"}, ... ],
        "deprecated_apis": [ {"api", "location", "replacement"}, ... ]
      },
      "since_last_review": [ {"id", "title", "status", "evidence"}, ... ]
                                      # optional; status is resolved | partial |
                                      # unresolved | obsolete
    }

Normalized review documents carry "status": "complete".

When a run cannot start the review — typically a non-interactive run with
nobody to ask — it records a needs-input document instead:

    {
      "status": "needs_input",
      "root": "<path>", "goal": "<the bare goal, if any>",
      "missing": ["goal" | "goal_specificity" | "file_list", ...],
      "question": "<what the caller must supply>",   # optional; defaulted
      "hypotheses": [ {"label", "goal", "scope": ["path", ...]}, ... ]
                                      # three or more when goal_specificity
                                      # is missing; candidates for the caller
                                      # to choose from, never a selection
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

NEEDS_INPUT = "needs_input"

# What a needs-input document can report as missing, with the default
# question put to the caller for each.
NEEDS_INPUT_QUESTIONS = {
    "goal": "What is the primary goal or use case Hindsight should evaluate this project against?",
    "goal_specificity": (
        "The stated goal is too broad to anchor a review. Pick one of the hypotheses "
        "below, blend them, or state a more specific goal."
    ),
    "file_list": (
        "The file list exceeds the 300-file guideline. Narrow the scope (a subdirectory "
        "or an explicit list), or explicitly accept the larger list."
    ),
}

MIN_HYPOTHESES = 3

# The Dependency Health Score is computed, never model-assigned: start at
# 100% and subtract a fixed amount per issue, floored at 0. A risky package
# counts more when its risk is verified by local evidence (lockfile
# deprecation, deprecated API in use) than when it rests on the model's
# unverified knowledge.
SCORE_DEDUCTIONS = [
    # (count key, singular label, plural label, points per issue)
    ("cycles", "circular dependency", "circular dependencies", 10),
    ("volatile_hubs", "volatile hub module", "volatile hub modules", 8),
    ("verified_risky_packages", "verified risky package", "verified risky packages", 8),
    ("unverified_risky_packages", "unverified risky package", "unverified risky packages", 4),
    ("deprecated_apis", "deprecated API use", "deprecated API uses", 5),
]

# Required text fields per scorecard list.
SCORECARD_LISTS = {
    "risky_packages": ("package", "basis"),
    "cycles": ("modules",),
    "volatile_hubs": ("module",),
    "deprecated_apis": ("api", "location"),
}

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

    doc = {k: v for k, v in data.items() if k not in ("findings", "no_findings")}
    doc["schema_version"] = SCHEMA_VERSION
    doc["status"] = "complete"
    doc["findings"] = []
    warnings = []
    for i, raw in enumerate(data["findings"], 1):
        finding, problem = normalize_finding(raw)
        if finding is None:
            warnings.append(f"dropped finding {i}: {problem}")
        else:
            doc["findings"].append(finding)

    entries = data.get("no_findings") or []
    if not isinstance(entries, list):
        warnings.append("no_findings is not an array; ignored")
        entries = []
    doc["no_findings"] = []
    for i, e in enumerate(entries, 1):
        if not isinstance(e, dict) or not text_field(e, "area") or not text_field(e, "reason"):
            warnings.append(f"dropped no_findings entry {i}: needs area and reason")
            continue
        doc["no_findings"].append({"area": normalize_area(text_field(e, "area")), "reason": text_field(e, "reason")})

    if "dependency_scorecard" in data:
        doc["dependency_scorecard"] = normalize_scorecard(data["dependency_scorecard"], warnings)
        if doc["dependency_scorecard"] is None:
            del doc["dependency_scorecard"]
    return doc, warnings


def normalize_scorecard(raw, warnings):
    """Normalize the dependency scorecard and compute its health score.
    Returns None (with a warning) if it isn't an object."""
    if not isinstance(raw, dict):
        warnings.append("dependency_scorecard is not an object; ignored")
        return None
    sc = {}
    if isinstance(raw.get("packages_reviewed"), int) and not isinstance(raw["packages_reviewed"], bool):
        sc["packages_reviewed"] = raw["packages_reviewed"]
    for key, required in SCORECARD_LISTS.items():
        entries = raw.get(key) or []
        if not isinstance(entries, list):
            warnings.append(f"dependency_scorecard.{key} is not an array; ignored")
            entries = []
        sc[key] = []
        for i, e in enumerate(entries, 1):
            if key == "cycles" and isinstance(e, list):
                e = {"modules": e}  # a bare module list, as import_graph.py prints
            if not isinstance(e, dict):
                warnings.append(f"dropped dependency_scorecard.{key} entry {i}: not an object")
                continue
            entry = {}
            for k, v in e.items():
                if k == "modules":
                    mods = [str(m).strip() for m in (v if isinstance(v, list) else [v]) if str(m).strip()]
                    if mods:
                        entry["modules"] = mods
                elif k == "verified":
                    entry["verified"] = v is True
                elif k == "fan_in":
                    if isinstance(v, int) and not isinstance(v, bool):
                        entry["fan_in"] = v
                elif isinstance(v, (str, int, float)) and str(v).strip():
                    entry[k] = str(v).strip()
            missing = [r for r in required if r not in entry]
            if missing:
                warnings.append(f"dropped dependency_scorecard.{key} entry {i}: missing {', '.join(missing)}")
                continue
            if key == "risky_packages":
                entry.setdefault("verified", False)
            sc[key].append(entry)
    if "health_score" in raw:
        warnings.append("dependency_scorecard.health_score is computed by the renderer; the supplied value was replaced")
    sc["health_score"], sc["score_breakdown"] = health_score(sc)
    return sc


def health_score(sc):
    """Return (score, breakdown) where breakdown lists (count, label, points)
    for each nonzero deduction."""
    counts = {
        "cycles": len(sc.get("cycles", [])),
        "volatile_hubs": len(sc.get("volatile_hubs", [])),
        "verified_risky_packages": sum(1 for p in sc.get("risky_packages", []) if p.get("verified")),
        "unverified_risky_packages": sum(1 for p in sc.get("risky_packages", []) if not p.get("verified")),
        "deprecated_apis": len(sc.get("deprecated_apis", [])),
    }
    breakdown = [[counts[key], singular if counts[key] == 1 else plural, points]
                 for key, singular, plural, points in SCORE_DEDUCTIONS if counts[key]]
    score = max(0, 100 - sum(n * points for n, _, points in breakdown))
    return score, breakdown


def normalize_needs_input(data):
    """Normalize a needs-input document. Returns (doc, warnings); raises
    ValueError if it doesn't say what is missing, or if a too-bare goal
    comes without at least MIN_HYPOTHESES hypotheses."""
    missing = data.get("missing")
    if isinstance(missing, str):
        missing = [missing]
    if not isinstance(missing, list) or not missing:
        raise ValueError('a needs_input document must list what is "missing"')
    unknown = [m for m in missing if m not in NEEDS_INPUT_QUESTIONS]
    if unknown:
        raise ValueError(
            f"unknown missing input(s) {unknown}; expected any of {list(NEEDS_INPUT_QUESTIONS)}"
        )

    doc = {k: v for k, v in data.items() if k not in ("missing", "hypotheses", "findings", "question")}
    doc["schema_version"] = SCHEMA_VERSION
    doc["status"] = NEEDS_INPUT
    doc["missing"] = missing
    doc["question"] = text_field(data, "question") or " ".join(NEEDS_INPUT_QUESTIONS[m] for m in missing)

    warnings = []
    doc["hypotheses"] = []
    hypotheses = data.get("hypotheses") or []
    for i, h in enumerate(hypotheses if isinstance(hypotheses, list) else [], 1):
        if not isinstance(h, dict) or not text_field(h, "label") or not text_field(h, "goal"):
            warnings.append(f"dropped hypothesis {i}: needs label and goal")
            continue
        scope = h.get("scope") or []
        if isinstance(scope, str):
            scope = [scope]
        doc["hypotheses"].append({
            "label": text_field(h, "label"),
            "goal": text_field(h, "goal"),
            "scope": [str(s).strip() for s in scope if str(s).strip()],
        })
    if "goal_specificity" in missing and len(doc["hypotheses"]) < MIN_HYPOTHESES:
        raise ValueError(
            f"a too-broad goal (goal_specificity) needs at least {MIN_HYPOTHESES} hypotheses, "
            f"got {len(doc['hypotheses'])}"
        )
    return doc, warnings


def load_document(data):
    """Dispatch on status: a needs-input document or a review document."""
    if isinstance(data, dict) and data.get("status") == NEEDS_INPUT:
        return normalize_needs_input(data)
    return normalize_document(data)


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
