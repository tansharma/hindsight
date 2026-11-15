# Scoped review: only what changed since a git ref

Reference for SKILL.md Step 1. Read it when the user asks to review only
what changed since a git ref: a branch, tag, or commit ("since main",
"what changed since v1.2", `--since <ref>`). Every other run is a full
review and never needs this file.

A scoped review updates the previous review rather than replacing it. It
reads only the changed files and the files that import them, re-checks the
previous findings those files touch, looks for new findings there, and
copies every other previous finding forward unchanged. It is cheaper and
faster, but it does not re-check anything outside the scope; say so when
offering it, and suggest a full review after large or cross-cutting changes.

## Before starting

- **A previous complete review must exist** (`inHindsight.json`, or the
  newest complete one in `hindsight-history/`, as in `re-runs.md`). With
  none there is nothing to carry forward: tell the user and run a full
  review instead (non-interactive: run the full review and say why in
  `summary`).
- The goal is still required (Step 1). Default to the previous review's
  `goal` only if the user confirms it, or the invocation says to reuse it.

## Step 1: the scoped file list

```bash
bash "<skill-dir>/scripts/list_files.sh" --root "<project_root>" --since "<ref>"
```

It lists the files changed between `<ref>` and the working tree
(committed, staged, unstaged, and new untracked files) plus their **direct
dependents** (the files that import a changed file, from the import graph),
with the usual filters (gitignore, secrets, binaries, Hindsight's own
outputs). Deleted files are not listed. Its stderr says
`Listed <n> of <total> file(s): …`; keep both numbers for the `scope`
block. It exits 1 for an unknown ref or a root outside git: say so and ask
for a valid ref (non-interactive: record a needs-input result with
`missing: ["file_list"]` and a `question` naming the ref that failed).

If it lists **no files**, nothing reviewable changed: do not render (that
would archive the current review for nothing). Tell the user the existing
`inHindsight.md` still stands (non-interactive: `HINDSIGHT: complete — 0
files changed since <ref> — <project_root>/inHindsight.md`).

The 300-file guideline applies to this list as it does to a full one.

## Step 2: what to read

- Read **only the scoped files**. Do not re-read the intent documents: the
  previous review already fixed the baseline. A changed README or design
  doc is in the list, so it is read anyway.
- Read the intent of the change instead: `git log --oneline <ref>..HEAD`
  and the commit messages it shows.
- Run `import_graph.py` on the **full** listing (`list_files.sh` without
  `--since`), not the scoped one, so cycles and hubs stay whole. It reads
  the files itself; you read only its JSON.

## Step 3: findings

A previous finding is **in scope** when its `evidence` cites a scoped
file, a directory holding one, or a path that no longer exists. The
renderer applies exactly this rule.

1. **In-scope previous findings:** verify and classify each one in
   `since_last_review` as `re-runs.md` describes (hand-set `status` is
   evidence, not proof); carry unresolved and partial ones forward under
   their `id`.
2. **New findings:** only in the scoped files, and each must cite at least
   one of them in `evidence`. A problem you notice outside the scope is not
   a finding in this run; mention it in `summary` and suggest a full review.
3. **Every other previous finding:** copy it from the previous
   `inHindsight.json` into `findings` **unchanged**: same `id` and every
   field as it was (drop only `evidence_unverified`). Do not re-rank,
   reword, or classify it; it gets no `since_last_review` entry.
4. **The rest of the document:** carry `no_findings` entries forward unless
   an in-scope finding now covers that area. In `gap_report`, keep previous
   entries whose `location` is outside the scope and re-assess the rest. In
   `dependency_scorecard`, take `cycles` and `volatile_hubs` from the full
   import graph, re-assess `risky_packages` and `deprecated_apis` only where
   a manifest, lockfile, or call site is in scope, carry the others, and
   never copy `health_score` (the renderer computes it). If the carried
   finding with the `decision_matrix` is untouched, keep it there and add no
   other matrix. Otherwise Step 4 picks the most critical finding as usual.
   Write a fresh `summary` about the change and what it did to the picture.

Add the scope to the findings document:

```json
"scope": {"since": "<ref>", "files": ["<every path list_files.sh --since printed>"], "total_files": <total>}
```

## Step 5: render

Render as usual (`--check` first). With a `scope` the renderer also warns
when a previous finding outside the scope is missing or changed, or when a
new finding cites no scoped file. Fix those before rendering. Only
in-scope previous findings need `since_last_review` entries. The rendered
Executive Summary states the scope (ref, files reviewed of total) and lists
the ids carried forward without re-verification, and `inHindsight.json`
records them as `scope.carried_forward`.
