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
  stderr).
- `common.sh` — helpers sourced by the shell scripts: the pruned-directory
  list, binary sniffing, the secret-filename patterns, and the shared
  `--files` / `--files-from` reader. Not run directly.
- `import_graph.py` — Step 2's dependency analysis for Python and JS/TS:
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
- `findings_schema.py` — the findings-document contract (documented in its
  docstring) shared by `render_output.py` and the legacy `parse_findings.py`: normalization, area and
  Impact/Effort canonicalization, and `H-NNN` id assignment. Not run
  directly.
- `render_output.py` — Step 5's renderer: findings document (or bare array)
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

The findings-document shape is defined once, in `findings_schema.py`'s
docstring. Change a field there and in SKILL.md Step 3 together. The
Health Score numbers live in `findings_schema.SCORE_DEDUCTIONS`;
`references/output-format.md` restates them (tested).

## The retired standalone pipeline

Before the skill ran end to end inside an agent, a scripted chain did the
review: `parse_args.sh` → `aggregate_context.sh` → `build_prompt.sh` →
(an LLM) → `parse_findings.py` → `render_output.py`. Nothing in the live
skill uses the first four, and `build_prompt.sh` was a second copy of the
review method that drifted from SKILL.md, so they now live in the
repository's `tests/fixtures/legacy_pipeline/` (still tested, not
installed). If you revive them, keep `build_prompt.sh`'s output format
and Impact/Effort rubric in step with SKILL.md (the rubric is tested) and
`parse_findings.py`'s `FIELD_ALIASES` in step with any field that should
parse from bold-label prose.
