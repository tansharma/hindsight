# Hindsight Skill

Hindsight is an advanced skill for experienced software engineers seeking deep architectural reviews. Instead of simple linting or isolated file checks, Hindsight analyzes your entire project structure and documentation against a defined functional goal.

**How it Works:** You define the primary purpose of your service (e.g., "This API handles user authentication"). Hindsight ingests up to 300 files/docs (a guideline you can override), reads the documentation first to learn what was intended, then judges the code against that intent and your goal. It proposes architectural improvements and ranks the findings by Impact/Effort.

**Current Scope:** Hindsight is an Agent Skill for Claude Code, Codex CLI, Gemini CLI, and GitHub Copilot. Each review produces `inHindsight.md` for people and `inHindsight.json` for scripts and agents. Each finding comes with a ready-to-paste fix prompt and a "Done when" check. The review also includes a Dependency Health Scorecard and tracks which earlier findings you've resolved. It requires an explicit goal, and can run unattended in CI or under another agent.

**Note** Project.md is there to provide project context only. When the scripted pipeline runs, `build_prompt.sh` does a `cat` on the whole file, and its headings and structure are dropped verbatim into the Project Context section of the prompt. It accepts `project.md`, `Project.md`, or `PROJECT.md`. The skill still runs without the file, but the model then has to infer project intent purely from the stated goal and the files it reads. **TL;DR** Add a Project.md to your repo with 3 defined sections: Idea, Ambition, Goal.

## Requirements

- One of the supported tools below, using whichever model it is configured with.
- `python3` 3.9 or newer and `bash` (3.2, the macOS default, is fine). They run the helper scripts in `hindsight/scripts/`. Nothing needs to be installed beyond the standard library.
- `git` (optional). In a git repository, Hindsight respects `.gitignore` when listing files and uses commit history to spot frequently changed modules.
- **Windows:** the `.sh` helpers need a bash, such as Git Bash or WSL. The Python helpers run natively.

## Integrating Hindsight into your workflow
Hindsight is a portable Agent Skill. The folder `hindsight/` contains a `SKILL.md` along with a `scripts/` helper directory. This folder works, unmodified, in Claude Code, Codex CLI, Gemini CLI, and GitHub Copilot. Each discovers skills the same way, from a `skills/` directory: personal (applies to all your projects) or project-level (applies only inside one repo).

The whole skill lives in the `hindsight/` folder at the root of this repo. To install it, copy that folder into the tool's `skills/` directory. Keep the folder name `hindsight` and keep `SKILL.md` plus `scripts/` together inside it. Nothing else in the repo is needed to use the skill. `tests/` is only for developing the skill further (see [Running the tests](#running-the-tests-for-skill-developers)), so you can ignore or delete it.

The commands below copy the folder *into* the `skills/` directory, so running the same command again updates an existing install in place. (Copying to `…/skills/hindsight` instead would nest a second `hindsight/` inside an existing install.) Files deleted from the skill in a newer version aren't removed by an update. To get an exact copy, delete the installed `hindsight` folder first.

### Claude Code

- **Personal** (every project): `~/.claude/skills/hindsight/`
- **Project-level** (this repo only): `.claude/skills/hindsight/` at the repo root

*macOS / Linux:*

```bash
mkdir -p ~/.claude/skills
cp -R hindsight ~/.claude/skills/
```

*Windows (PowerShell):*

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\skills" | Out-Null
Copy-Item -Recurse -Force hindsight "$env:USERPROFILE\.claude\skills"
```

For a project-level install, use `.claude/skills` (`.claude\skills` on Windows) at the repo root as the destination instead.

No restart needed. Claude Code picks up skills added under `~/.claude/skills/` (`%USERPROFILE%\.claude\skills\` on Windows) or `.claude/skills/` within the current session. Invoke it by typing `/hindsight` in Claude Code, or just describe the task ("do a hindsight review of this project") and Claude will trigger the skill from its description.

### Codex CLI

- **Personal**: `~/.codex/skills/hindsight/`
- **Project-level**: `.codex/skills/hindsight/` at the repo root

*macOS / Linux:*

```bash
mkdir -p ~/.codex/skills
cp -R hindsight ~/.codex/skills/
```

*Windows (PowerShell):*

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force hindsight "$env:USERPROFILE\.codex\skills"
```

For a project-level install, use `.codex/skills` (`.codex\skills` on Windows) at the repo root instead.

Codex scans both directories at session startup and loads skills automatically based on their description. Invoke with `/hindsight`, or describe the task in prose.

### Gemini CLI

- **Personal**: `~/.gemini/skills/hindsight/` (alias: `~/.agents/skills/hindsight/`)
- **Project-level**: `.gemini/skills/hindsight/` at the repo root (alias: `.agents/skills/hindsight/`)

*macOS / Linux:*

```bash
mkdir -p ~/.gemini/skills
cp -R hindsight ~/.gemini/skills/
```

*Windows (PowerShell):*

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.gemini\skills" | Out-Null
Copy-Item -Recurse -Force hindsight "$env:USERPROFILE\.gemini\skills"
```

The `~/.agents/skills/` alias maps to `%USERPROFILE%\.agents\skills\` on Windows; use whichever your Gemini CLI install already has set up. For a project-level install, use `.gemini/skills` (or `.agents/skills`) at the repo root instead.

Confirm it's discovered with `/skills list`, then invoke with `/hindsight` or by describing the task.

### GitHub Copilot

Copilot supports Agent Skills in VS Code agent mode, the Copilot CLI, the Copilot app, and the Copilot cloud agent. Install Hindsight like any other skill:

- **Personal**: `~/.copilot/skills/hindsight/` (alias: `~/.agents/skills/hindsight/`; VS Code also reads `~/.claude/skills/`)
- **Project-level**: `.github/skills/hindsight/` at the repo root (aliases: `.agents/skills/hindsight/`, `.claude/skills/hindsight/`)

*macOS / Linux:*

```bash
mkdir -p ~/.copilot/skills
cp -R hindsight ~/.copilot/skills/
```

*Windows (PowerShell):*

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.copilot\skills" | Out-Null
Copy-Item -Recurse -Force hindsight "$env:USERPROFILE\.copilot\skills"
```

For a project-level install, use `.github/skills` (`.github\skills` on Windows) at the repo root instead. A project-level `.claude/skills/hindsight/` install is shared by Claude Code and Copilot.

Copilot matches your request against the skill's description, so "do a hindsight review of this project against goal X" loads it. In VS Code it is also available as the `/hindsight` slash command.

*Older Copilot versions without Agent Skills:* point Copilot at the skill through repository custom instructions instead. Add a line like "For architectural reviews, follow `hindsight/SKILL.md` and its `hindsight/scripts/` helpers" to `.github/copilot-instructions.md`, keeping the `hindsight/` folder in the repo.

### Using the skill (Claude Code, Codex, Gemini, Copilot)

However you invoke it, Hindsight needs three inputs up front to run:

1. **Project root** — The directory to review.
2. **File list**    — Which files to scan. If you name only a directory, Hindsight lists it the same way every time: it respects `.gitignore` and skips dependency and build folders, binaries, secret-looking files such as `.env`, and its own earlier output. The cap is ~300 files, as a guideline; it asks before going over it.
3. **User goal**    — A defined purpose or use case for the project (e.g. "this service handles payment processing"). This is mandatory: Hindsight will stop and ask for it if you omit it. If the goal you give is too bare to anchor a review (e.g. "make it faster"), Hindsight will instead propose three concrete hypotheses for what you likely mean, each with a short checklist of the files/modules that matter for it, and ask you to pick one before continuing.


Example invocation:

```text
/hindsight review this repo against the goal "low-latency read path for a payment API", scanning everything under src/
```

Hindsight writes its findings to `inHindsight.md` at the project root. Findings are grouped by Impact/Effort, then by area (Architectural Patterns, Code Quality, Documentation Gaps). Every area is addressed: one with genuinely nothing to report is listed under "No Findings" with the reason, rather than padded with a nit. Each finding has a stable ID (`H-001`, `H-002`, …) and includes the area, the issue, the retrospective rationale, an Impact/Effort ranking, the evidence, a "Done when" check for knowing the fix is complete, and a ready-to-paste LLM prompt to fix it (with the "Done when" check appended, so the agent you paste it into knows when to stop).

Evidence is checked, not just printed. Before writing the review, Hindsight checks every citation against your files: the path must exist, the line must be in range, and a quoted excerpt must appear at the line it cites. On a re-run it also checks that every earlier finding has been classified. Citations that fail are corrected before the review is written, and any left unverified are marked in `inHindsight.json`.

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

## Running the tests (for skill developers)

You don't need this section, or the `tests/` directory, to install or use Hindsight. It's for anyone changing the skill itself.

The helper scripts in `hindsight/scripts/` have a regression suite in `tests/` (Python standard library only, nothing to install). From the repo root:

```bash
python3 -m unittest discover -s tests -v
```

`tests/` sits outside `hindsight/` on purpose, so it isn't copied when you install the skill.

### Accuracy and consistency eval (opt-in, costs money)

The unit tests cover the scripts; they can't tell you whether reviews are *right*. `tests/eval/` runs the installed skill headlessly on a small fixture project (`orders-svc`) with known planted issues (an architectural drift from the README's promise, a duplicated workaround, a stale doc claim, and an instruction aimed at AI reviewers), plus a fake secret. It then grades each `inHindsight.json` mechanically: which planted issues were found (matched by cited file and line), whether the secret or the injected command leaked, whether every area was addressed, and how much evidence the renderer couldn't verify. Across runs it shows how often each planted issue was found and which Impact/Effort bucket it landed in, which is a direct measure of consistency.

```bash
bash tests/eval/run.sh                          # prints the spending cap, runs nothing
bash tests/eval/run.sh --yes --runs 2 --budget 1.00
```

Each run is capped with `claude --max-budget-usd`, so the most it can cost is runs × budget; a full review cost about $0.65 in earlier headless checks. It evaluates the copy in `~/.claude/skills/hindsight` (it warns when that differs from this repo's `hindsight/`), needs the `claude` CLI, and never runs as part of `python3 -m unittest discover -s tests`. The fake secret and the injected comment are written into a temporary copy at run time, so neither is committed here. The grader works on its own too: `python3 tests/eval/grade.py --expected tests/eval/fixtures/orders-svc.expected.json <inHindsight.json>...`.

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
| 14 | Claim verification. Evidence paths, lines, and verbatim quotes checked against the project; re-run coverage checked against the previous review; `--check` validates without writing, so corrections don't renumber findings. | Done | /scripts/verify_findings.py, /scripts/render_output.py |
| 15 | Review accuracy. Import graph ignores TYPE_CHECKING and type-only imports and reports deferred imports; one Impact/Effort rubric shared by SKILL.md and the P-Prompt; opt-in eval harness with planted-issue fixture and a deterministic grader. | Done | /scripts/import_graph.py, SKILL.md Step 3, tests/eval/ |
