[Hindsight](index.md) › Using

# Using Hindsight

This works the same in Claude Code, Codex, Gemini, and Copilot. However you invoke it, Hindsight needs three inputs up front to run:

1. **Project root** — The directory to review.
2. **File list**    — Which files to scan. If you name only a directory, Hindsight lists it the same way every time: it respects `.gitignore` and skips dependency and build folders, binaries, secret-looking files such as `.env`, and its own earlier output. The cap is ~300 files, as a guideline; it asks before going over it.
3. **User goal**    — A defined purpose or use case for the project (e.g. "this service handles payment processing"). This is mandatory: Hindsight will stop and ask for it if you omit it. If the goal you give is too bare to anchor a review (e.g. "make it faster"), Hindsight will instead propose three concrete hypotheses for what you likely mean, each with a short checklist of the files/modules that matter for it, and ask you to pick one before continuing.

Example invocation:

```text
/hindsight review this repo against the goal "low-latency read path for a payment API", scanning everything under src/
```

## What a review produces

Hindsight writes its findings to `inHindsight.md` at the project root. Findings are grouped by Impact/Effort, then by area (Architectural Patterns, Code Quality, Documentation Gaps). Every area is addressed: one with genuinely nothing to report is listed under "No Findings" with the reason, rather than padded with a nit. Each finding has a stable ID (`H-001`, `H-002`, …) and includes the area, the issue, the retrospective rationale, an Impact/Effort ranking, the evidence, a "Done when" check for knowing the fix is complete, and a ready-to-paste LLM prompt to fix it (with the "Done when" check appended, so the agent you paste it into knows when to stop).

Evidence is checked, not just printed. Before writing the review, Hindsight checks every citation against your files: the path must exist, the line must be in range, and a quoted excerpt must appear at the line it cites. On a re-run it also checks that every earlier finding has been classified. Citations that fail are corrected before the review is written, and any left unverified are marked in `inHindsight.json`.

Alongside it, Hindsight writes `inHindsight.json`: the same findings in machine-readable form, for scripts or coding agents that want to pick up a finding by ID ("implement H-003 from inHindsight.json") without parsing Markdown.

The JSON's shape is defined in the docstring of `hindsight/scripts/findings_schema.py`. A review document has `schema_version`, `status` (`complete`, or `needs_input` when a run stopped to ask for something), `root`, `goal`, `generated`, `summary`, and `findings`. Each finding has `id`, `area`, `title`, `issue`, `rationale`, `impact`, `effort`, `evidence` (strings like `path:42`, or `{path, line, quote}` objects), `prompt`, `done_when`, and, when a citation failed verification, `evidence_unverified`. Alongside the findings are `no_findings`, `gap_report`, `dependency_scorecard` (with its computed `health_score`), and `since_last_review`.

Those are the only files Hindsight writes; it never modifies your project's code directly. Run it again later in the same project and it will also report which of its previous findings you've since resolved, keeping each carried-forward finding's ID. Before writing a new review, it moves the previous `inHindsight.md`/`.json` into `hindsight-history/` with a timestamp, so earlier reviews are never lost. You may want to add `hindsight-history/` to your `.gitignore`.

## Decision matrix, gap report, and scorecard

For the single most critical finding in each review, Hindsight also generates a weighted decision matrix: three or more distinct candidate solutions scored by Estimated Impact and Development Effort (1-5), rendered as a table directly beneath that finding — so the highest-leverage issue comes with options to weigh, not just one prescribed fix.

Hindsight also cross-references every Documentation Gaps finding against the actual code: it lists the specific public functions, classes, and interfaces missing a doc-comment (in whatever convention is idiomatic to that language) or a usage example in the primary docs, as a Cross-Reference Gap Report at the end of `inHindsight.md`.

Every review also includes a **Dependency Health Scorecard**, a quantitative view of architectural risk from third-party packages and internal coupling. It lists high-risk packages, circular imports between your modules, "volatile hub" modules (imported by many others, but full of TODO/FIXME markers or changed constantly), and calls to deprecated APIs. It also gives a Health Score computed by a fixed, visible formula. For Python and JavaScript/TypeScript, circular imports and volatile hubs come from a deterministic script, so that part of the score is reproducible; risky packages and deprecated APIs are identified by the model, so the score can vary between runs. Package risk is judged from local evidence only (manifests, lockfiles, the code itself), with no network calls. Anything that rests on the model's own knowledge is marked "unverified".

Next: [Running unattended](unattended.md)
