[Hindsight](index.md) › Running unattended

# Running unattended (CI, headless, or from another agent)

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

Next: [Helper scripts](scripts.md)
