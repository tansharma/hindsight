[Hindsight](index.md) › Installing

# Installing Hindsight

## Requirements

- One of the supported tools below, using whichever model it is configured with.
- `python3` 3.9 or newer and `bash` (3.2, the macOS default, is fine). They run the helper scripts in `hindsight/scripts/`. Nothing needs to be installed beyond the standard library.
- `git` (optional). In a git repository, Hindsight respects `.gitignore` when listing files and uses commit history to spot frequently changed modules.
- **Windows:** the `.sh` helpers need a bash, such as Git Bash or WSL. The Python helpers run natively.

## Get the skill

Clone the repository; the commands on this page run from its root:

```bash
git clone https://github.com/tansharma/hindsight.git
cd hindsight
```

## Integrating Hindsight into your workflow

Hindsight is a portable Agent Skill. The folder `hindsight/` contains a `SKILL.md` along with a `scripts/` helper directory and a `references/` directory the agent reads only when needed. This folder works, unmodified, in Claude Code, Codex CLI, Gemini CLI, and GitHub Copilot. Each discovers skills the same way, from a `skills/` directory: personal (applies to all your projects) or project-level (applies only inside one repo).

The whole skill lives in the `hindsight/` folder at the root of the repo. To install it, copy that folder into the tool's `skills/` directory. Keep the folder name `hindsight` and keep `SKILL.md`, `scripts/`, and `references/` together inside it. Nothing else in the repo is needed to use the skill. `tests/` is only for developing the skill further (see [Developing the skill](development.md)), so you can ignore or delete it.

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

Next: [Using Hindsight](usage.md)
