# Hindsight output format

Reference for SKILL.md Step 5. `scripts/render_output.py` produces this
structure; you only need this file if `python3` is unavailable and the
files must be written by hand. The Health Score numbers below restate
`SCORE_DEDUCTIONS` in `scripts/findings_schema.py`, which is the source of
truth (a test checks the two agree).

Contents:
- `inHindsight.md` structure — the full rendered template
- What the renderer guarantees
- `inHindsight.json` — the sidecar's shape

## `inHindsight.md` structure

````markdown
# In Hindsight — <project name>

- **Project root:** ... / **User goal:** ... / **Generated:** ... / **Total findings:** ...

## Executive Summary
<summary, then the finding count by area>

## Since Last Review          <!-- only on re-runs; see Step 6 -->
<n> previous finding(s): <tally>.
- **H-001 <title>** — Resolved: <evidence>

## ⚡ High Impact / Low Effort
### <Area>
#### H-002. <title>
- **Issue:** ...
- **Rationale:** ...
- **Impact/Effort:** High Impact / Low Effort
- **Evidence:** `path:line`
- **Done when:** ...

**LLM Action Prompt**

```text
<prompt verbatim>

Done when:
<done_when verbatim>
```

**Decision Matrix**          <!-- only on the single most critical finding; see Step 4 -->
| Solution Name | Estimated Impact (1-5) | Development Effort (1-5) | Argument |

## 🏗️ High Impact / High Effort
...
## 🧹 Low Impact / Low Effort
...
## 🕐 Low Impact / High Effort
...

## ✅ No Findings          <!-- only for areas with a no_findings entry -->
### <Area>
<reason>

## 🔗 Dependency Health Scorecard
**Health Score: 82%** — 100 − 1 × 10 (circular dependency) − 2 × 4 (unverified risky packages) = 82
### High-Risk Third-Party Packages      <!-- each list shows "None found." when empty -->
### Circular Dependencies
### Volatile Hub Modules
### Deprecated API Usage

## 📋 Cross-Reference Documentation Gap Report     <!-- see Step 3 -->
| Element Name | Type | Suggested Location |
|---|---|---|
| ... | Function/Class/Interface | ... |
````

## What the renderer guarantees

Follow these when writing the files by hand:

- The four Impact/Effort sections appear in exactly that priority order;
  a bucket with zero findings is omitted rather than printed empty.
- Within each bucket, findings are sub-grouped by Area under `###`
  headers — findings from different areas are never interleaved.
- Each `prompt` is reproduced **verbatim**, followed by its `done_when`,
  inside a code fence longer than any fence the prompt itself contains; it
  is the text the user copies out, so it is never summarized or edited.
- The `**Decision Matrix**` subsection appears under exactly one finding —
  the single most critical one from Step 4.
- The `Cross-Reference Documentation Gap Report` appears **once**, after
  the four buckets, and is omitted entirely (not an empty table) when
  `gap_report` is empty.
- An area with a `no_findings` entry is listed under `## ✅ No Findings`
  with its reason; an entry for an area that does have findings is ignored
  with a warning.
- The `Dependency Health Scorecard` always shows all four lists ("None
  found." for an empty one) and a Health Score computed as 100% minus 10
  per circular dependency, 8 per volatile hub module, 8 per verified
  risky package, 4 per unverified risky package, and 5 per deprecated API
  use,
  floored at 0 (`SCORE_DEDUCTIONS` in `scripts/findings_schema.py`), with
  the arithmetic printed beside it. A score in the input is replaced. If
  the document has no `dependency_scorecard`, the section is omitted with
  a warning.

## `inHindsight.json`

The normalized findings document: the contract in the docstring of
`scripts/findings_schema.py`, with `schema_version`, `status`
(`complete` or `needs_input`), `generated`, every finding's `id`, and
`evidence_unverified` on findings whose citations failed verification.
