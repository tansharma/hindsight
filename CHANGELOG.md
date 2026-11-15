# Changelog

All notable changes to Hindsight. Versions follow [Semantic Versioning](https://semver.org/):
a major version changes the findings contract (`inHindsight.json`) or the
skill's inputs incompatibly, a minor version adds a capability, and a patch
fixes behaviour without adding one.

The version is defined once, as `metadata.version` in `hindsight/SKILL.md`'s
frontmatter. Every review records the version that wrote it, as
`hindsight_version` in `inHindsight.json` and on the Generated line of
`inHindsight.md`. To release, bump that line, add an entry here, and update
the version in the `docs/` page footers (the tests check that all three
agree).

## [Unreleased]

### Removed
- The retired standalone pipeline (`parse_args.sh`, `aggregate_context.sh`,
  `build_prompt.sh`, `parse_findings.py`, `mock_review.txt`) from
  `tests/fixtures/legacy_pipeline/`, with its 45 tests, and the file-list
  reader in `common.sh` that only it used. None of it shipped with the skill;
  it remains in git history (`git show 19b853a:tests/fixtures/legacy_pipeline/`).
  The renderer still accepts the pre-JSON finding keys.

### Changed
- `docs/install.html` labels every Windows PowerShell command as untested.

## [1.0.0] — 2026-11-15

First versioned release. Reviews written before it have no
`hindsight_version`.

### Added
- Versioning: `metadata.version` in SKILL.md, this changelog, the version
  stamped into `inHindsight.json`/`.md`, and the version in the site footer.
- `export_tasks.py`: open findings as id-keyed Markdown tasks in a
  `## Hindsight` section (idempotent), or printed `gh issue create` commands.
- `rollup.py`: one page across several projects' reviews (health score,
  open/resolved, age, trend), flagging reviews older than 60 days.
- Scoped reviews: `list_files.sh --since <git-ref>` (changed files plus direct
  dependents), a `scope` block, and carry-forward checks in the renderer.
- `set_status.py`: mark a finding resolved, partial, or wontfix between
  reviews; shown as a badge, verified (not trusted) by the next review.
- Swift support in `import_graph.py`: target-level graph from SwiftPM
  `Package.swift` and XcodeGen `project.yml`, with `Package.resolved` pins.

## Before 1.0.0 (unversioned)

- **2026-10-22** SKILL.md progressive disclosure: conditional procedures moved
  into `references/`.
- **2026-10-21** Claim verification (evidence paths, lines, quotes; re-run
  coverage; `render_output.py --check`), review accuracy fixes (type-only
  imports, Impact/Effort rubric), the opt-in paid eval harness, the docs site
  in `docs/`, and the legacy pipeline retired to `tests/fixtures/`.
- **2026-10-21** Dependency Health Scorecard with the deterministic import
  graph (Python, JS/TS) and computed Health Score.
- **2026-10-20** JSON findings contract with stable `H-NNN` ids, archived
  history, non-interactive mode and safety guardrails, script hardening.
- **2026-07-15** Weighted Decision Matrix, Cross-Reference Documentation Gap
  Report, and the Goal Refinement Hypothesis Engine.
- **2026-07-14** First version: the `/hindsight` skill, the scripted
  pipeline, and the sample `Project.md`.
