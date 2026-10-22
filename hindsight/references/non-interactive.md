# Non-interactive runs

Reference for SKILL.md "Execution Modes". Read it when the run is
non-interactive (a headless run, CI, or Hindsight running as a subagent);
interactive runs never need it.

In non-interactive mode, **never ask a question and never guess the
answer to one.** Every place Step 1 would stop and ask instead records a
**needs-input** result (Step 1 says which), renders it, and ends the run:

```bash
python3 "<skill-dir>/scripts/render_output.py" --root "<project_root>" <<'NEEDS'
{"status": "needs_input", "missing": ["goal"], "goal": "<bare goal, if one was given>",
 "hypotheses": [{"label": "...", "goal": "...", "scope": ["path", "..."]}]}
NEEDS
```

`missing` lists any of `goal`, `goal_specificity`, `file_list`;
`hypotheses` (three or more) is required for `goal_specificity`. The
renderer writes a short status page to `inHindsight.md` and the document
to `inHindsight.json`, archiving any previous review into
`hindsight-history/` first. If `project_root` itself is unknown there is
nowhere to write, so skip the render.

**End every non-interactive run with a fixed first line** in your final
message, so a calling script or agent can branch on it without parsing
prose:

- `HINDSIGHT: complete — <n> findings — <project_root>/inHindsight.md`
- `HINDSIGHT: needs-input — missing: <comma-separated list>` (followed by
  the question and, for `goal_specificity`, the hypotheses)
