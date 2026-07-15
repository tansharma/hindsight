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
3. **User goal**    — A defined purpose or use case for the project (e.g. "this service handles payment processing"). This is mandatory, Hindsight will stop and ask for it if you omitted.


Example invocation:

```text
/hindsight review this repo against the goal "low-latency read path for a payment API", scanning everything under src/
```

Hindsight writes its findings to `inHindsight.md` at the project root. Each finding includes the area, the issue, the retrospective rationale, an Impact/Effort ranking, and a ready-to-paste LLM prompt to fix it. 

Hindsight **only ever writes that one file**; it never modifies your project's code directly. Run it again later in the same project and it will also report which of its previous findings you've since resolved.

## Tasklog

| # | Task | Status | Notes|
|---|------|--------|------|
| 1 | Setup Project Structure and Input Handling. Create a core skill wrapper module  | Done  | /scripts/parse_args.sh        |
| 2 | Directory Scanning and Context Aggregation. Implement file reading service.     | Done  | /scripts/aggregate_context.sh |
| 3 | Prompt Generation / Goal Framing. Develop a primary prompt template.            | Done  | /scripts/build_prompt.sh      |
| 4 | Structured Output Parsing. Implement parsing logic for the LLM's response.      | Done  | /scripts/parse_findings.py    |
| 5 | Output Generation (`inHindsight.md`). Develop a module to render the output.    | Done  | /scripts/render_output.py     |
| 6 | User Feedback Integration Loop. Implement basic tracking logic.                 | Done  |                               |
