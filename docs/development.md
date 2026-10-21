[Hindsight](index.md) › Developing the skill

# Running the tests (for skill developers)

You don't need this page, or the `tests/` directory, to install or use Hindsight. It's for anyone changing the skill itself.

The helper scripts in `hindsight/scripts/` have a regression suite in `tests/` (Python standard library only, nothing to install). From the repo root:

```bash
python3 -m unittest discover -s tests -v
```

`tests/` sits outside `hindsight/` on purpose, so it isn't copied when you install the skill.

## Accuracy and consistency eval (opt-in, costs money)

The unit tests cover the scripts; they can't tell you whether reviews are *right*. `tests/eval/` runs the installed skill headlessly on a small fixture project (`orders-svc`) with known planted issues (an architectural drift from the README's promise, a duplicated workaround, a stale doc claim, and an instruction aimed at AI reviewers), plus a fake secret. It then grades each `inHindsight.json` mechanically: which planted issues were found (matched by cited file and line), whether the secret or the injected command leaked, whether every area was addressed, and how much evidence the renderer couldn't verify. Across runs it shows how often each planted issue was found and which Impact/Effort bucket it landed in, which is a direct measure of consistency.

```bash
bash tests/eval/run.sh                          # prints the spending cap, runs nothing
bash tests/eval/run.sh --yes --runs 2 --budget 1.00
```

Each run is capped with `claude --max-budget-usd`, so the most it can cost is runs × budget; a full review cost about $0.65 in earlier headless checks. It evaluates the copy in `~/.claude/skills/hindsight` (it warns when that differs from this repo's `hindsight/`), needs the `claude` CLI, and never runs as part of `python3 -m unittest discover -s tests`. The fake secret and the injected comment are written into a temporary copy at run time, so neither is committed here. The grader works on its own too: `python3 tests/eval/grade.py --expected tests/eval/fixtures/orders-svc.expected.json <inHindsight.json>...`.
