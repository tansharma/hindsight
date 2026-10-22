# Re-runs: track what was acted on

Reference for SKILL.md Step 6. Read it when a previous review exists
(`inHindsight.json`, an older `inHindsight.md`, or `hindsight-history/` at
the project root); a first review never needs this file.

Before writing the new review, check whether a previous one exists:

1. **Extract prior findings** from `<project_root>/inHindsight.json` — each
   has a stable `id`, its `issue`, and its `done_when`. If that file's
   `status` is `needs_input` (the last run stopped for input and produced no
   review), use the newest `*-inHindsight.json` in `hindsight-history/`
   whose `status` is `complete` instead. If only an older `inHindsight.md`
   exists (from before the JSON sidecar), read the findings from its
   headings and Issue/Rationale fields.
2. **Verify each against the current code** — not against memory of the
   last run. A prior finding's `done_when` is the first thing to check.
   Classify each as:
   - **resolved** — the code now reflects the suggested change (cite the
     evidence: file, function, or doc that changed).
   - **partial** — started but incomplete; say what remains.
   - **unresolved** — unchanged.
   - **obsolete** — no longer applicable (the code it referred to was
     removed, or the goal changed).
3. **Record the result in `since_last_review`** — one entry per prior
   finding: `{"id", "title", "status", "evidence"}`. The renderer prints
   the `## Since Last Review` section immediately after the Executive
   Summary and computes the tally line itself.
4. **Carry unresolved and partial findings forward** into the new
   document's `findings` **with their original `id`**, re-ranked if
   circumstances changed, so the new review is always the single complete,
   current picture and its ids line up with the last one. Give genuinely
   new findings no id; the renderer numbers them after the previous run's
   highest id, so a number is never reused for a different finding.

The renderer cross-checks this against the previous review: `--check`
warns about a previous id missing from `since_last_review`, an entry for
an id the previous review didn't have, and an unresolved or partial
finding that wasn't carried forward under its id. It archives the
previous `inHindsight.md`/`.json` into `hindsight-history/` before writing
the new pair — no manual copying is needed.
