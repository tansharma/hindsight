#!/usr/bin/env bash
# Opt-in accuracy and consistency eval for Hindsight. Plants an eval
# fixture in a temp dir, runs the *installed* skill on it headlessly N times
# (`claude -p '/hindsight …'`), and grades every inHindsight.json with
# tests/eval/grade.py. This spends money, so it never runs as part of
# `python3 -m unittest discover -s tests`, and it does nothing without --yes.
#
# Usage:
#   tests/eval/run.sh                    # print the cost cap and exit
#   tests/eval/run.sh --yes [--runs 2] [--budget 1.00] [--fixture orders-svc] [--out <dir>]
#
# --budget is the per-run cap passed to `claude --max-budget-usd`; the most
# a run can cost is --runs × --budget. Reviews and logs are kept in --out
# (default: a new temp dir), one runN/ per run.
#
# The installed skill (~/.claude/skills/hindsight) is what gets evaluated.
# If it differs from this repo's hindsight/, a warning says so — refresh it
# first to evaluate the working tree. CLAUDE_BIN overrides the `claude`
# binary (the regression tests point it at a stub), and
# HINDSIGHT_EVAL_ALLOWED_TOOLS overrides the headless tool allowlist.
#
# Exit codes:
#   0  cost printed (no --yes), or every run met the recall bar with no leaks
#   1  bad arguments, a failed run, or grade.py reported a failure

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"

runs=2
budget="1.00"
fixture="orders-svc"
out=""
yes=0

usage() {
  echo "Usage: $0 [--yes] [--runs N] [--budget USD] [--fixture NAME] [--out DIR]" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) yes=1; shift ;;
    --runs|--budget|--fixture|--out)
      [[ $# -ge 2 ]] || usage
      case "$1" in
        --runs) runs="$2" ;;
        --budget) budget="$2" ;;
        --fixture) fixture="$2" ;;
        --out) out="$2" ;;
      esac
      shift 2
      ;;
    -h|--help) usage ;;
    *) echo "Unknown argument: $1" >&2; usage ;;
  esac
done

[[ "$runs" =~ ^[1-9][0-9]*$ ]] || { echo "Error: --runs must be a positive integer." >&2; exit 1; }
[[ "$budget" =~ ^[0-9]+(\.[0-9]+)?$ ]] || { echo "Error: --budget must be a dollar amount." >&2; exit 1; }

expected="$here/fixtures/$fixture.expected.json"
[[ -f "$expected" ]] || { echo "Error: no fixture '$fixture' ($expected)." >&2; exit 1; }

cap="$(python3 -c "import sys; print(f'{int(sys.argv[1]) * float(sys.argv[2]):.2f}')" "$runs" "$budget")"
echo "Hindsight eval: $runs run(s) of fixture '$fixture', at most \$$budget each — up to \$$cap in total."
if (( ! yes )); then
  echo "Nothing was run. Re-run with --yes to spend up to \$$cap."
  exit 0
fi

claude_bin="${CLAUDE_BIN:-claude}"
command -v "$claude_bin" >/dev/null 2>&1 || { echo "Error: '$claude_bin' not found on PATH." >&2; exit 1; }

installed="$HOME/.claude/skills/hindsight"
if [[ -z "${CLAUDE_BIN:-}" ]] && ! diff -rq -x __pycache__ -x .DS_Store "$repo/hindsight" "$installed" >/dev/null 2>&1; then
  echo "Warning: $installed differs from $repo/hindsight; the installed copy is what gets evaluated." >&2
fi

goal="$(python3 -c "import json, sys; print(json.load(open(sys.argv[1]))['goal'])" "$expected")"
out="${out:-$(mktemp -d "${TMPDIR:-/tmp}/hindsight-eval.XXXXXX")}"
mkdir -p "$out"

reviews=()
for i in $(seq 1 "$runs"); do
  project="$out/run$i/$fixture"
  mkdir -p "$out/run$i"
  python3 "$here/plant.py" --expected "$expected" --dest "$project"
  git -C "$project" init -q
  git -C "$project" add -A
  git -C "$project" -c user.name=hindsight-eval -c user.email=eval@localhost commit -qm "fixture"
  echo "Run $i/$runs: reviewing $project ..."
  if ! ( cd "$project" && HINDSIGHT_NONINTERACTIVE=1 "$claude_bin" -p \
        "/hindsight review . against the goal \"$goal\"" \
        --max-budget-usd "$budget" --output-format json --no-session-persistence \
        --allowedTools "${HINDSIGHT_EVAL_ALLOWED_TOOLS:-Bash Read Write Glob Grep Skill}" ) > "$out/run$i/claude.json" 2> "$out/run$i/claude.err"; then
    echo "Error: run $i failed; see $out/run$i/claude.err" >&2
    exit 1
  fi
  if [[ ! -f "$project/inHindsight.json" ]]; then
    echo "Error: run $i wrote no inHindsight.json; see $out/run$i/claude.json" >&2
    exit 1
  fi
  reviews+=("$project/inHindsight.json")
done

echo
echo "Reviews and logs: $out"
python3 "$here/grade.py" --expected "$expected" "${reviews[@]}"
