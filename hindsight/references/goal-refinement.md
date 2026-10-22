# Goal refinement (Hypothesis Engine)

Reference for SKILL.md Step 1, item 4. Read it only when the user's goal is
genuinely bare (it names no target dimension, subsystem, or business
process); a goal that names one, even loosely, never needs this file.

For a genuinely bare goal:

- Do a **lightweight structural skim only** — the directory tree and
  top-level READMEs, not the full `file_list` contents (that read
  happens in Step 2, after scope is settled, so it isn't spent on a
  goal the user is about to redirect).
- From that skim, identify the project's apparent core business
  processes or functional areas (e.g. payments, auth, ingestion).
- Generate **three distinct, concrete hypotheses** for what the real
  objective might be, each with a short label, a restated concrete
  goal, and a mini-scope checklist of the key files/modules that would
  need immediate review to test that specific hypothesis.
- **Stop and present all three; do not proceed.** Ask the user to pick
  one, blend them, or state their own refined goal instead. Treat
  whatever they confirm as the `user_goal` for the rest of the review.
  A hypothesis is a candidate for the user to choose, never a
  replacement the skill decides on its own — the same "never infer the
  goal" rule from item 3 applies here to each individual hypothesis.
- *Non-interactive:* record a needs-input result with
  `missing: ["goal_specificity"]`, the bare goal, and all three
  hypotheses — the caller picks one and re-runs. Never pick one
  yourself.
