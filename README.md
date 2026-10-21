# Hindsight Skill

Hindsight is an advanced skill for experienced software engineers seeking a deep architectural reviews. Instead of simple linting or isolated file checks, Hindsight analyzes your entire project structure and documentation against a defined functional goal.

**How it Works:** You define the primary purpose of your service (e.g., "This API handles user authentication"). Hindsight ingests up to 300 files/docs, cross-references the code for technical debt, proposes architectural improvements, and ranks these findings by Impact/Effort.

**Current Scope:** Initial implementation is a CLI skill that generates a structured `inHindsight.md` file containing actionable recommendations grouped by severity (Impact/Effort). This version requires explicit user goal input to operate.

**Note** Project.md is there to provide project context only. `build_promt.sh` does a `cat` on the whole file and any headings, structure gets dropped verbatim into the Project Context section of the prompt. The skill will still run without the Project.md file, but the LLM would need to infer project intent purely from the specified goal and aggregated file contents. **TL;DR** Add a Project.md to your repo with 3 defined sections, Idea, Ambition, Goal. 

## Integrating Hindsight into your workflow
Hindsight is a portable Agent Skill. The folder `hindsight/` contains a `SKILL.md` along with a `scripts/` helper directory. This folder works, unmodified, in Claude Code, Codex CLI, and Gemini CLI — as each of these tools discovers skills the same way and picks them up from a `skills/` directory, either personal/global (applies to all your projects) or at project-level (applies only inside your chosen repo). GitHub Copilot has no equivalent skills-discovery mechanism, so it's wired up differently — see the Copilot section below.

The whole skill lives in the `hindsight/` folder at the root of this repo. To install it, copy that folder. Keep the folder name `hindsight` and keep `SKILL.md` plus `scripts/` together inside it.

### Claude Code

- **Global/Personal**   copy to `~/.claude/skills/hindsight/`
- **Project Level**     copy to `.claude/skills/hindsight/` at the repo root

No restart needed. Claude Code picks up skills added under `~/.claude/skills/` or `.claude/skills/` within the current session. Invoke it by typing `/hindsight` in Claude Code, or just describe the task ("do a hindsight review of this project") and Claude will trigger the skill from its description.

### Codex CLI

- **Global/Personal**: copy to `~/.codex/skills/hindsight/`
- **Project Level**:   copy to `.codex/skills/hindsight/` at the repo root

Codex scans both directories at session startup and loads skills automatically based on their description. Invoke with `/hindsight`, or
describe the task in prose.

### Gemini CLI

- **Global/Personal**: copy to `~/.gemini/skills/hindsight/` (alias: `~/.agents/skills/hindsight/`)
- **Project-only**:    copy to `.gemini/skills/hindsight/` at the repo root (alias: `.agents/skills/hindsight/`)

Confirm it's discovered with `/skills list`, then invoke with `/hindsight` or by describing the task.

### Using the skill (Claude Code, Codex, Gemini)

However you invoke it, Hindsight needs three inputs up front to run

1. **Project root** — The directory to review.
2. **File list**    — Which files to scan (defaults to enumerating the project root, capped at ~300 files as a guideline).
3. **User goal**    — A defined purpose or use case for the project (e.g. "this service handles payment processing"). This is mandatory, Hindsight will stop and ask for it if you omitted. If the goal you give is too bare to anchor a review (e.g. "make it faster"), Hindsight will instead propose three concrete hypotheses for what you likely mean, each with a short checklist of the files/modules that matter for it, and ask you to pick one before continuing.


Example invocation:

```text
/hindsight review this repo against the goal "low-latency read path for a payment API", scanning everything under src/
```

Hindsight writes its findings to `inHindsight.md` at the project root. Each finding has a stable ID (`H-001`, `H-002`, …) and includes the area, the issue, the retrospective rationale, an Impact/Effort ranking, the evidence, a "Done when" check for knowing the fix is complete, and a ready-to-paste LLM prompt to fix it (with the "Done when" check appended, so the agent you paste it into knows when to stop).

Alongside it, Hindsight writes `inHindsight.json`: the same findings in machine-readable form, for scripts or coding agents that want to pick up a finding by ID ("implement H-003 from inHindsight.json") without parsing Markdown.

Those are the only files Hindsight writes; it never modifies your project's code directly. Run it again later in the same project and it will also report which of its previous findings you've since resolved, keeping each carried-forward finding's ID. Before writing a new review, it moves the previous `inHindsight.md`/`.json` into `hindsight-history/` with a timestamp, so earlier reviews are never lost. You may want to add `hindsight-history/` to your `.gitignore`.

For the single most critical finding in each review, Hindsight also generates a weighted decision matrix: three or more distinct candidate solutions scored by Estimated Impact and Development Effort (1-5), rendered as a table directly beneath that finding — so the highest-leverage issue comes with options to weigh, not just one prescribed fix.

Hindsight also cross-references every Documentation Gaps finding against the actual code: it lists the specific public functions, classes, and interfaces missing a doc-comment (in whatever convention is idiomatic to that language) or a usage example in the primary docs, as a Cross-Reference Gap Report at the end of `inHindsight.md`.

Every review also includes a **Dependency Health Scorecard**, a quantitative view of architectural risk from third-party packages and internal coupling. It lists high-risk packages, circular imports between your modules, "volatile hub" modules (imported by many others, but full of TODO/FIXME markers or changed constantly), and calls to deprecated APIs. It also gives a Health Score computed by a fixed, visible formula, so the same project gets the same score. For Python and JavaScript/TypeScript, the import graph is computed by a script rather than estimated. Package risk is judged from local evidence only (manifests, lockfiles, the code itself), with no network calls. Anything that rests on the model's own knowledge is marked "unverified".

## Running unattended (CI, headless, or from another agent)

When nobody can answer Hindsight's questions — `claude -p`, `codex exec`, a CI job, or another agent delegating the review — run it in non-interactive mode by saying so in the invocation ("non-interactive", "--yes") or by setting `HINDSIGHT_NONINTERACTIVE=1`. Hindsight also switches on its own when it is plainly running without a person (for example as a subagent).

In that mode it never asks and never guesses. It builds the file list deterministically, respecting `.gitignore` and skipping dependency folders, binaries, and secret-looking files such as `.env` and `*.pem`. When an input is missing it writes a "needs input" status to `inHindsight.json` and `inHindsight.md` instead of a review, and archives any previous review first. The missing input can be the goal, a goal too broad to review against (it then includes three goal hypotheses to choose from), or a file list over the cap. Its final message always starts with one of two lines a script can check:

```text
HINDSIGHT: complete — 7 findings — /path/to/project/inHindsight.md
HINDSIGHT: needs-input — missing: goal
```

```bash
HINDSIGHT_NONINTERACTIVE=1 claude -p '/hindsight review . against the goal "low-latency reads for the payment API"'
```

Whatever the mode, Hindsight treats the files it reviews as data. Instructions embedded in them are never followed or copied into the prompts it writes, and secret values never appear in its output.

## Running the tests

The helper scripts in `hindsight/scripts/` have a regression suite in `tests/` (Python standard library only, nothing to install). From the repo root:

```bash
python3 -m unittest discover -s tests -v
```

`tests/` sits outside `hindsight/` on purpose, so it isn't copied when you install the skill.

## Tasklog

| # | Task | Status | Notes|
|---|------|--------|------|
| 1 | Setup Project Structure and Input Handling. Create a core skill wrapper module  | Done  | /scripts/parse_args.sh        |
| 2 | Directory Scanning and Context Aggregation. Implement file reading service.     | Done  | /scripts/aggregate_context.sh |
| 3 | Prompt Generation / Goal Framing. Develop a primary prompt template.            | Done  | /scripts/build_prompt.sh      |
| 4 | Structured Output Parsing. Implement parsing logic for the LLM's response.      | Done  | /scripts/parse_findings.py    |
| 5 | Output Generation (`inHindsight.md`). Develop a module to render the output.    | Done  | /scripts/render_output.py     |
| 6 | User Feedback Integration Loop. Implement basic tracking logic.                 | Done  |                               |
| 7 | Weighted Decision Matrix Generator. Score 3+ candidate solutions for the single most critical finding. | Done | /scripts/render_decision_matrix.py |
| 8 | Cross-Reference Documentation Gap Detection. List public elements missing doc-comments/usage examples. | Done | SKILL.md Steps 3 & 5 (prompt-only) |
| 9 | Goal Refinement Hypothesis Engine. Propose 3 concrete hypotheses when the stated goal is too bare. | Done | SKILL.md Step 1 item 4 (prompt-only) |
| 10 | Script hardening. Fix parser/renderer/input edge cases, keep reads inside the project root, resolve script paths from the skill dir, add a regression suite. | Done | /scripts/*, tests/test_scripts.py |
| 11 | JSON findings contract. Findings as a JSON document with stable IDs and required "Done when"; full-template renderer; `inHindsight.json` sidecar; timestamped `hindsight-history/` on re-runs. | Done | /scripts/findings_schema.py, /scripts/render_output.py |
| 12 | Agentic mode and safety. Non-interactive mode with needs-input status files and a fixed result line; deterministic file listing; secret-file skipping; untrusted-content guardrails; explicit "no findings" per area. | Done | /scripts/list_files.sh, /scripts/common.sh, SKILL.md Execution Modes |
| 13 | Dependency Health Scorecarding. Risky packages, circular imports, volatile hub modules, and deprecated API use, with a formula-computed Health Score; local evidence only. | Done | /scripts/import_graph.py, SKILL.md Steps 2-3 & 5 |
