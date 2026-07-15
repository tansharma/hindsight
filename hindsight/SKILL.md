---
name: hindsight
description: >
  Deep retrospective architectural review of an entire project against a
  user-stated goal, producing ranked, actionable findings in inHindsight.md.
  Use this skill whenever the user runs "/hindsight", asks for an
  "architectural review", "codebase review", "technical debt review", or
  "hindsight review", asks "what should I improve here", "what would you have
  done differently", or "review this project against my goal", or wants to
  re-check which previously reported findings have been resolved. Trigger even
  if the user doesn't name the skill but describes reviewing a whole project
  (not a single file) against a purpose or goal. Requires the user to state
  the project's goal; writes the review to inHindsight.md at the project root.
---

# Hindsight — Retrospective Architectural Review

Hindsight reviews an entire project the way a Senior Technical Architect
reviews a system that has already been built: with full knowledge of how it
turned out. It is for experienced (mid-to-senior) engineers, so findings
should be substantive — not linting, not style nits, not isolated-file
observations. Every run produces one deliverable: `inHindsight.md` at the
project root, containing findings ranked by Impact/Effort, each with a
ready-to-paste LLM prompt that would fix it.

## The Hindsight Principle

The skill is named for a specific kind of judgment: understanding that is
only available *after* the fact. Decisions that were reasonable — even
obviously correct — when they were made can turn out to be wrong once the
whole project exists and its real purpose is known. That is the judgment this
review must apply, and it is what separates Hindsight from a linter or a
per-file code review.

In practice this means the review happens in two distinct passes:

1. **Reconstruct what was intended.** Before judging anything, learn what the
   authors believed and planned *at the time*: READMEs, design docs, ADRs,
   spec files, TODO/FIXME comments, and — when the project is a git
   repository — the commit history (`git log --oneline` shows the order in
   which decisions solidified). Record intent as written, before reading the
   code that resulted from it.
2. **Judge the outcome against that intent and the user's goal.** Now read
   the code knowing how the story ended. Where did the project drift from its
   own stated intent? Which early decisions, sensible then, are clearly
   holding the goal back now? Where did the same workaround get repeated
   until it became load-bearing?

The test for a high-value finding: *would this have been visible on day one
from a single file, or does it only become obvious now, with the whole
project, its history, and its goal in view?* Both kinds are reportable, but
the retrospective kind is why this skill exists — prioritize it.

## Step 1 — Collect and Validate the Three Required Inputs

Do not begin the review until all three are known. Parse them from the
`/hindsight` invocation in whatever form the user supplied them — flags,
prose, or earlier conversation; there is no fixed CLI syntax.

1. **`project_root`** — the directory to analyze. If not supplied, ask;
   default to the current working directory only if the user confirms.
2. **`file_list`** — the files to scan, recommended cap **300**.
   - An explicit list from the user is used as-is. If it exceeds 300,
     recommend narrowing scope; only proceed past the cap if the user
     knowingly accepts it (the cap is a resource guideline, not a hard
     limit — larger models and smaller files can handle more).
   - Given only a directory, enumerate the files under `project_root`
     (skip `.git/`, build artifacts, binaries, and vendored dependencies)
     and confirm the resulting list and count with the user before
     proceeding, especially near the cap.
3. **`user_goal`** — a concrete purpose or use case (e.g. "This service
   handles payment processing", "Optimize for low read latency"). This is
   **mandatory** and is what every finding must be judged against. If the
   user has not stated one, stop and ask: "What is the primary goal or use
   case Hindsight should evaluate this project against?" Never fabricate or
   infer the goal — a review anchored to a guessed goal produces confident,
   wrong priorities.

Once valid, restate the scope in one compact confirmation before analyzing,
so the user can catch a mis-scoped run early:

```json
{ "root": "<path>", "files": ["<path1>", "..."], "goal": "<string>" }
```

Then proceed — do not wait for a reply unless something looked ambiguous.

## Step 2 — Ingest: Documentation First, Then Code

Build the full review context. Read documentation **before** code — that
ordering is what keeps the retrospective honest, because it fixes "what was
intended" in place before "what actually happened" can color it.

1. **Directory structure.** Produce a short, high-level orientation of
   `project_root` (a depth-limited tree or a plain-language summary).
2. **Intent sources.** Read READMEs, design/spec docs, ADRs, and changelogs
   first, and skim the git history if present. Note explicit claims,
   promises, and assumptions — these become the baseline the code is judged
   against in Step 3.
3. **File contents.** Read every path in `file_list`. If a file cannot be
   read (missing, binary, permission error), skip it and note the omission —
   never fabricate contents, never abort the whole run over one bad path.
4. **Report coverage.** State how many files were read versus skipped
   (e.g. "Read 42/45 files; 3 skipped: ...") so the user can sanity-check
   what the review actually saw.

## Step 3 — The Retrospective Analysis

Adopt the persona of a **Senior Technical Architect** conducting a
post-hoc review for a mid-to-senior engineering audience. Analyze the full
context from Step 2 relative to `user_goal` — every finding must be
justified against that goal specifically, not against generic best practice.

Cover all three areas, with **at least one finding in each**:

- **Architectural Patterns** — structural and design-level issues: coupling
  that grew instead of being chosen, abstractions the project outgrew,
  patterns that fit the original idea but not the stated goal.
- **Code Quality** — implementation-level issues in the actual files:
  accumulated technical debt, duplicated workarounds, fragile contracts
  between components that only history explains.
- **Documentation Gaps** — docs that are missing, stale, or actively
  misleading relative to what the code now does and what the goal needs.

Write each finding with these five bold-labeled fields, in this order. (This
exact `**Label**` format is a contract: `scripts/parse_findings.py` splits
findings on each `**Area**` label and recognizes only these five labels — do
not add new bold-labeled fields or rename these.)

- **Area** — one of the three areas above.
- **Issue** — what is wrong, concretely, naming files/modules.
- **Rationale** — the retrospective judgment, in three beats: what made this
  choice reasonable (or invisible) at the time; what is clear *now* that the
  whole project and its history are in view; and why it matters to the
  user's stated goal. This field is where the hindsight lives — a rationale
  that could have been written on day one belongs to a linter, not here.
- **Impact/Effort** — exactly one of: "High Impact / Low Effort",
  "High Impact / High Effort", "Low Impact / Low Effort",
  "Low Impact / High Effort".
- **Suggested LLM Action Prompt** — a self-contained prompt the user can
  paste into any coding agent to implement the fix. It must name the
  specific files, describe the current state, state the desired end state,
  and restate the relevant slice of `user_goal` — the agent receiving it
  will not have this review as context.

Group related symptoms into one finding with one root cause rather than
listing each symptom separately — the user acts on findings, and five
findings with the same fix are one finding.

## Step 4 — Weighted Decision Matrix: The Single Most Critical Finding

Every finding from Step 3 carries one `Suggested LLM Action Prompt` — a
single fix. For the **one** finding that matters most, a single fix
understates the decision: there is usually more than one reasonable way to
address it, and the trade-off between them is exactly what a senior
engineer wants surfaced, not decided for them by the review.

1. **Identify the single most critical finding** across all areas and
   buckets from Step 3 — the one whose resolution would move `user_goal`
   the most. This is normally the (or a) High Impact / Low Effort finding;
   if none exists, take the highest-impact finding overall. Exactly one
   finding gets this treatment, no matter how many findings the review has.
2. **Generate three or more genuinely distinct candidate solutions** for
   that finding's root cause — not the same fix worded three ways. Each
   candidate needs:
   - `solution` — a short name for the approach.
   - `impact` — estimated impact, 1 (marginal) to 5 (transformative),
     scored against `user_goal`.
   - `effort` — estimated development effort, 1 (trivial) to 5 (major
     undertaking).
   - `argument` — one or two sentences on why this candidate scores as it
     does, and its main risk or trade-off.
3. **Render the comparison** with `scripts/render_decision_matrix.py`,
   passing the candidates as a JSON array:

   ```bash
   echo '<JSON array of candidates>' | scripts/render_decision_matrix.py
   ```

   The script drops any candidate missing a required field or with
   impact/effort outside 1-5, then prints a four-column Markdown table
   (Solution Name, Estimated Impact, Development Effort, Argument). It
   exits 1 if fewer than three valid candidates remain — if that happens,
   there isn't a real decision to present; fold the rationale for the
   single viable approach back into that finding's `Rationale` instead of
   forcing a matrix.
4. **Attach the table to the finding**, not in place of its existing
   fields — see the `**Decision Matrix**` subsection in the Step 5
   template below. The finding keeps its normal `Issue`, `Rationale`,
   `Impact/Effort` bucket placement, and its own `Suggested LLM Action
   Prompt`; the matrix is additional context for choosing between
   approaches, appended directly beneath it.

Every other finding is unaffected — this step runs exactly once per
review, only for the single most critical finding.

## Step 5 — Rank and Render `inHindsight.md`

Render the findings into `<project_root>/inHindsight.md`. This step is
presentation: every finding appears exactly once, none are added, dropped,
or re-worded.

Use this exact structure:

````markdown
# In Hindsight — <project name>

## Executive Summary
<What was reviewed, against what goal, how many findings, the one-paragraph
"knowing what we know now" verdict.>

## Since Last Review          <!-- only on re-runs; see Step 6 -->
...

## ⚡ High Impact / Low Effort
### <Area>
#### <n>. <short finding title>
- **Issue:** ...
- **Rationale:** ...

**LLM Action Prompt**
```text
<LLM_Prompt verbatim>
```

**Decision Matrix**          <!-- only on the single most critical finding; see Step 4 -->
<rendered table from scripts/render_decision_matrix.py>

## 🏗️ High Impact / High Effort
...
## 🧹 Low Impact / Low Effort
...
## 🕐 Low Impact / High Effort
...
````

Rules:

- Emit the four Impact/Effort sections in exactly that priority order; omit
  any bucket with zero findings instead of printing an empty header.
- Within each bucket, sub-group by Area under `###` headers — never
  interleave findings from different areas.
- Reproduce each `LLM_Prompt` **verbatim** inside its fenced code block; it
  is the field the user copies out, so it must never be summarized or edited
  during rendering.
- The `**Decision Matrix**` subsection appears under exactly one finding —
  the single most critical one identified in Step 4 — never under more
  than one, and never in place of that finding's own fields.

## Step 6 — Re-Runs: Track What Was Acted On

Success for Hindsight is measured by whether the user *implements* its
suggestions — so every run after the first must close the loop.

Before writing the new file, check whether `<project_root>/inHindsight.md`
already exists:

1. **Extract prior findings** from the existing file (its structure is the
   template above, so headings and Issue/Rationale fields identify each
   finding).
2. **Verify each against the current code** — not against memory of the
   last run. Classify each as:
   - **Resolved** — the code now reflects the suggested change (cite the
     evidence: file, function, or doc that changed).
   - **Partially resolved** — started but incomplete; say what remains.
   - **Unresolved** — unchanged.
   - **Obsolete** — no longer applicable (the code it referred to was
     removed, or the goal changed).
3. **Render a `## Since Last Review` section** immediately after the
   Executive Summary: a one-line tally (e.g. "5 previous findings: 2
   resolved, 1 partial, 2 unresolved") followed by one line per prior
   finding with its status and evidence.
4. **Carry unresolved and partial findings forward** into the new review's
   buckets, re-ranked if circumstances changed, so the new `inHindsight.md`
   is always the single complete, current picture.

Then overwrite `inHindsight.md` with the new review. The old file's content
lives on in the `Since Last Review` accounting; do not keep versioned copies
unless the user asks.

## Guardrails

- Hindsight **reviews**; it does not modify the user's code. The only file
  it writes is `inHindsight.md`.
- Never invent findings to fill an area. If an area genuinely has nothing
  worth reporting (rare in practice), say so explicitly in that area's
  section rather than manufacturing a nit.
- Never weaken a finding because it implicates a recent or deliberate
  decision — retrospective judgment of reasonable-at-the-time decisions is
  the entire point.
- Never manufacture Decision Matrix candidates to hit the three-solution
  minimum. If the single most critical finding truly has only one
  reasonable approach, say so in that finding's `Rationale` and skip the
  matrix rather than padding it with near-duplicate options.

## Deterministic Helper Scripts

`scripts/` contains a deterministic counterpart for each pipeline stage, for
testing the stages without a model and as the basis for automated tests.
They chain:

```bash
scripts/parse_args.sh --root <path> --goal "<use case>" [--files "a.py,b.py,..."]
scripts/aggregate_context.sh --root <path> --files "a.py,b.py,..." \
  | scripts/build_prompt.sh --root <path> --goal "<use case>" \
  # execute the printed P-Prompt against an LLM, then:
  | scripts/parse_findings.py \
  | scripts/render_output.py --root <path> --goal "<use case>"
```

- `parse_args.sh` — validates the three inputs (exit 1 on missing
  root/goal or >300 files) and prints the Step 1 confirmation JSON.
- `aggregate_context.sh` — prints a depth-3 directory tree plus
  `--- FILE: <path> ---` demarcated contents; skips missing files with a
  stderr warning and logs read/missing/byte counts.
- `build_prompt.sh` — assembles the architect P-Prompt from root, goal, and
  the context block (stdin or `--context-file`); pure templating, no LLM
  call.
- `parse_findings.py` — parses an executed review's prose into a JSON array
  of `{Area, Issue, Rationale, Impact/Effort, LLM_Prompt}` objects; splits
  on `**Area**` labels, tolerates minor label punctuation variance, drops
  incomplete findings, exits 1 if none parse. `scripts/mock_review.txt` is
  a hand-written 3-finding review for exercising it without an LLM.
- `render_output.py` — groups the JSON findings by Impact/Effort then Area
  and writes `inHindsight.md` (`--out` to override); off-spec Impact/Effort
  labels render in their own section rather than being dropped.
- `render_decision_matrix.py` — Step 4's renderer. Takes a JSON array of
  `{solution, impact, effort, argument}` candidates (stdin or a file arg)
  and prints a four-column Markdown table; drops any candidate missing a
  field or with `impact`/`effort` outside 1-5, and exits 1 if fewer than
  three valid candidates remain. Independent of the `parse_findings.py` /
  `render_output.py` pair above — it does not touch the five-label finding
  contract, so it can be changed on its own.

```bash
echo '[{"solution": "...", "impact": 1-5, "effort": 1-5, "argument": "..."}, ...]' \
  | scripts/render_decision_matrix.py
```

Format coupling to respect: `parse_findings.py`'s label regex assumes Step
3's bold-label output format, and `render_output.py`'s Area grouping is a
loose substring match. Change the finding format in Step 3 and these two
scripts together, or not at all.
