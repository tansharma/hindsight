# Hindsight helper scripts

Reference for maintainers and for debugging a failed run; SKILL.md lists
only the commands a review runs. All scripts live in `scripts/`, use only
the Python 3.9+ standard library and bash 3.2+, and never touch the
network. Regression tests: `python3 -m unittest discover -s tests -v` from
the repository root (`tests/` is not installed with the skill).

## Scripts

- `list_files.sh` — Step 1's deterministic enumeration: prints the files to
  review under `--root`, one per line, sorted. Respects `.gitignore` in a
  git work tree; always skips dependency/build dirs, Hindsight's own
  outputs (`inHindsight.md`/`.json`, `hindsight-history/`), symlinks,
  binaries, and secret-looking files (naming each secret it skips on
  stderr). `--since <git-ref>` (a scoped review,
  `references/scoped-review.md`) lists only the files that changed between
  the ref and the working tree (`git diff --relative <ref> -- .` plus
  untracked, not-ignored files), after the same filters, plus their direct
  dependents from `import_graph.py --dependents-of`; deleted files are not
  listed. Exits 1 outside a git work tree or for an unknown ref.
- `common.sh` — helpers sourced by `list_files.sh`: the pruned-directory
  list, binary sniffing, and the secret-filename patterns. Not run
  directly.
- `import_graph.py` — Step 2's dependency analysis for Python, JS/TS and Swift.
  `--dependents-of <changed.txt>` prints, instead of the JSON, the listed
  files that directly import a changed file (module-level or deferred; for
  Swift, every listed file of a target that imports the changed file's
  target), sorted, without the changed files. For Python and JS/TS:
  internal import graph (Python via `ast`; resolves package, `src/`-layout,
  relative, same-directory, and nested-project-root imports; skips `TYPE_CHECKING`-guarded and
  TypeScript type-only imports), function-local `deferred_imports` (they
  count toward fan-in but not toward cycles), circular-import sets (Tarjan's
  algorithm), volatile hubs (fan-in ≥ 3 plus a comment marker or top-quartile
  git churn ≥ 5), imported external packages (stdlib and Node built-ins
  excluded), declared packages from `package.json` / `requirements*.txt` /
  `pyproject.toml`, and `package-lock.json` deprecations. Output is sorted
  and deterministic; no network access. Syntax errors are reported in
  `parse_errors`, not fatal.
  **Swift** is analysed per build target, in the same output shape, without
  calling the Swift toolchain. Targets come from each `Package.swift`
  (regex: `.target`, `.executableTarget`, `.testTarget`, `.macro`,
  `.plugin` with a literal `name:`; `path:` or the `Sources/<name>` /
  `Tests/<name>` defaults) and each XcodeGen `project.yml` (line parsing of
  every target's `sources`), found in a listed Swift file's directory or
  any ancestor up to the root, so a repository with several packages
  works. A module entry is one target: `path` is its source directory,
  `language` is `swift`, `markers` sums its files' comment markers, and
  `churn` counts commits touching any of its files. Each listed Swift file
  belongs to the target whose source path is its longest prefix; its
  `import X` lines (including `@testable import` and `import struct X.Y`,
  comments stripped) become edges to target `X`. Imports that match no
  target and no Apple/toolchain module go to `external_packages` with the
  importing files, keyed by the package identity when a
  `.product(name:, package:)` entry or a `Package.resolved` pin names it,
  otherwise by the module name. `Package.resolved` pins (format 1-3, next
  to a manifest or inside an `.xcodeproj`/`.xcworkspace` beside one) are
  added to `declared_packages` as identity → version. Limits: targets
  built from variables or loops in `Package.swift`, SwiftPM `exclude:` /
  `sources:`, XcodeGen `include:` files, flow-style target mappings and
  `PRODUCT_MODULE_NAME` overrides are not read; Swift files outside every
  detected target (including a hand-made `.xcodeproj` with no manifest)
  count as `unsupported_files`.
- `findings_schema.py` — the findings-document contract (documented in its
  docstring) used by `render_output.py`: normalization, area and
  Impact/Effort canonicalization, and `H-NNN` id assignment. Not run
  directly.
- `render_output.py` — Step 5's renderer. Stamps `hindsight_version` (from
  SKILL.md's `metadata.version`, via `findings_schema.skill_version`) into
  both outputs, replacing any supplied value. With a `scope` in the document
  (a scoped review), it states the scope in the Executive Summary, records
  `scope.carried_forward`, requires `since_last_review` entries only for
  the previous findings in scope, and warns when a previous finding outside
  the scope is missing or changed, or a new finding cites no scoped file
  (rules in `verify_findings.py`'s docstring). The rest of this entry
  applies to every review: findings document (or bare array)
  in, `inHindsight.md` + `inHindsight.json` out (`--out` / `--json-out` to
  override; `--root`/`--goal` may instead come from the document). Archives
  any previous pair into `hindsight-history/`, assigns ids without reusing
  any number from the current output or the archive, maps loosely worded
  Impact/Effort values to the four buckets (truly off-spec labels get their
  own section rather than being dropped), sizes each prompt's code fence so
  a prompt containing its own ``` block can't break out, and renders the
  Decision Matrix, Since Last Review, No Findings, Dependency Health
  Scorecard (with its computed Health Score), and Gap Report sections;
  warns about any area with neither a finding nor a `no_findings` entry.
  Checks claims via `verify_findings.py` (below). Exits 1 if more than one
  finding carries a `decision_matrix`. `--check` runs everything but
  writes and archives nothing, exiting 0 (clean) or 2 (warnings). A
  needs-input document (Execution Modes) renders as a short status page
  instead, with the question and any goal hypotheses.
- `verify_findings.py` — the claim checks `render_output.py` runs, as
  warnings: evidence paths exist under the root, cited lines are in range,
  evidence quotes appear (whitespace-insensitively) within 3 lines of the
  cited line; on a re-run, `since_last_review` classifies every previous
  finding and unresolved/partial ones are carried forward under their id.
  Not run directly.
- `set_status.py` — run by the user (or by the agent when asked) between
  reviews, never during one: `--root <path> --id H-004 --status
  resolved|partial|wontfix --note "..." [--commit <sha>]`. Sets the
  finding's optional `status`, `status_note` and `status_commit` in
  `inHindsight.json` and rewrites `inHindsight.md` from that document with
  `render_output.render`, in place: nothing is archived, no id changes,
  and `generated` keeps the review's date. A call replaces the previous
  status entirely, so repeating it leaves both files byte-identical. The
  renderer shows the status as a badge beside the title plus a Status line
  that says it was marked by hand. Exits 1 (files untouched) for a missing
  or needs-input review, an unknown id, an empty note, or a malformed
  commit; the commit is format-checked only, not looked up in git. On the
  next review the status is prior evidence the reviewer verifies
  (`references/re-runs.md`).
- `export_tasks.py` — not part of a review: `--root <path> --format
  markdown --target pending.md` or `--format gh`. Exports the open findings
  (not hand-marked resolved/wontfix) of `<root>/inHindsight.json`.
  markdown keeps a `## Hindsight` section in the target (appended, and the
  file created, if missing): one task per finding between
  `<!-- hindsight:begin H-NNN -->` / `<!-- hindsight:end H-NNN -->`
  markers, with a checkbox line (id, title, rank, area) and the prompt plus
  `done_when` in a fence sized past any backticks in it. Keyed by id:
  existing tasks are rewritten in place (the user's checkbox is kept), new
  ones appended after the last task, closed ones ticked with `— closed:
  <reason>` rather than deleted; text outside the markers is untouched,
  and the file is written only when its text changes, so a repeat export
  is byte-identical. Task lines are indented, so prompt text can't fake a
  marker or a heading. gh prints a bash script of `gh issue create`
  commands and runs nothing: titles go through `shlex.quote`, bodies through
  `--body-file -` and a quoted heredoc whose delimiter no body line equals.
  Exits 1 for a missing or needs-input review or an unreadable/unwritable
  target, 2 for bad arguments.
- `rollup.py` — not part of a review: `--roots <root> ... [--out
  rollup.md] [--stale-days 60] [--today YYYY-MM-DD]` reads each root's
  `inHindsight.json` and `hindsight-history/*.json` and writes one section
  per project: a one-row table for the latest complete review (health
  score, open, resolved, won't-fix, review date, age in days) and a trend
  line across every complete review (date, health score, open count, and
  the first-to-last change). Open is the latest review's findings minus
  those hand-marked resolved/wontfix; resolved is distinct ids ever
  classified resolved in `since_last_review` plus hand-marked ones. A
  review more than `--stale-days` old is flagged in its row, under the
  project, and in the page header. A review's date is `generated`, else the
  archive filename's date, else the file's mtime. Missing roots, unreadable
  or truncated files, and needs-input runs are noted per project, never
  fatal. Exits 1 only for a bad `--today`/`--stale-days` or an unwritable
  `--out`. Test fixtures: `tests/fixtures/rollup/` (re-included in
  `.gitignore`).
- `render_decision_matrix.py` — the table renderer `render_output.py` uses
  for Step 4. Also usable on its own to preview a matrix: takes a JSON
  array of `{solution, impact, effort, argument}` candidates (stdin or a
  file arg), drops any missing a field or with `impact`/`effort` outside
  1-5, and exits 1 if fewer than three valid candidates remain.

Preview a decision matrix on its own (`S=<skill-dir>/scripts`):

```bash
python3 "$S/render_decision_matrix.py" <<'CANDIDATES'
[{"solution": "...", "impact": 1-5, "effort": 1-5, "argument": "..."}, ...]
CANDIDATES
```

## Format coupling

The release version is `metadata.version` in SKILL.md's frontmatter;
`CHANGELOG.md`'s newest entry and the `docs/` footers restate it, and a
test fails if they disagree. Release steps are at the top of
`CHANGELOG.md`.

The findings-document shape is defined once, in `findings_schema.py`'s
docstring. Change a field there and in SKILL.md Step 3 together. The
Health Score numbers live in `findings_schema.SCORE_DEDUCTIONS`;
`references/output-format.md` restates them (tested).
