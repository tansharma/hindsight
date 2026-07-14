#!/usr/bin/env bash
# T3 test script: assembles the primary directive prompt ("P-Prompt") that
# will be sent to the core LLM to perform the actual architectural review.
# This script is purely deterministic templating — it does not call an LLM
# and does not analyze anything itself; it only combines project.md, the
# mandatory user_goal, and the aggregated file context (T2's output) into a
# single ready-to-inject prompt string.
#
# Usage:
#   scripts/aggregate_context.sh --root <path> --files "a.py,b.py,..." | \
#     scripts/build_prompt.sh --root <path> --goal "<use case>"
#
#   # or, with a pre-saved context block:
#   scripts/build_prompt.sh --root <path> --goal "<use case>" \
#     --context-file <path/to/context.txt>
#
# Behavior:
#   - Reads project context from <root>/project.md (warns and substitutes a
#     placeholder if missing, rather than failing the whole run).
#   - Reads the aggregated file/context block from --context-file if given,
#     otherwise from stdin (intended to be piped straight from
#     aggregate_context.sh).
#   - Prints the fully assembled P-Prompt to stdout. Nothing else is written
#     to stdout; progress/diagnostics go to stderr.
#
# Exit codes:
#   0  P-Prompt assembled and printed
#   1  a required input is missing or invalid

set -euo pipefail

root=""
goal=""
context_file=""

usage() {
  echo "Usage: $0 --root <path> --goal \"<use case>\" [--context-file <path>]" >&2
  echo "  If --context-file is omitted, the file context block is read from stdin." >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      root="${2:-}"
      shift 2
      ;;
    --goal)
      goal="${2:-}"
      shift 2
      ;;
    --context-file)
      context_file="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      ;;
  esac
done

if [[ -z "$root" ]]; then
  echo "Error: --root <project_root> is required." >&2
  exit 1
fi

if [[ -z "$goal" ]]; then
  echo "Error: --goal <user_goal> is mandatory (Hindsight requires a defining use case/goal)." >&2
  exit 1
fi

if [[ ! -d "$root" ]]; then
  echo "Error: --root '$root' is not a directory." >&2
  exit 1
fi

project_md="$root/project.md"
if [[ -f "$project_md" ]]; then
  project_context="$(cat "$project_md")"
else
  echo "Warning: no project.md found at $project_md; substituting a placeholder." >&2
  project_context="(no project.md found at $project_md — no project context available)"
fi

if [[ -n "$context_file" ]]; then
  if [[ ! -f "$context_file" ]]; then
    echo "Error: --context-file '$context_file' not found." >&2
    exit 1
  fi
  file_context="$(cat "$context_file")"
else
  if [[ -t 0 ]]; then
    echo "Error: no --context-file given and stdin is a terminal — nothing to read." >&2
    usage
  fi
  file_context="$(cat)"
fi

if [[ -z "$file_context" ]]; then
  echo "Warning: file context block is empty; the P-Prompt will have no codebase content to analyze." >&2
fi

cat <<PPROMPT
You are acting as a Senior Technical Architect conducting a comprehensive, evidence-based review of the codebase below, on behalf of an experienced (mid-to-senior) engineering audience.

## Project Context
$project_context

## User Goal (mandatory — evaluate everything against this)
"$goal"

Every finding you raise must be justified in terms of how it helps or hinders this stated goal. Do not raise generic best-practice nitpicks that have no bearing on the goal.

## Codebase Context
$file_context

## Your Task
Analyze the project above and identify concrete improvement opportunities across all three of the following areas — you must cover at least one finding in each:
1. **Architectural Patterns** — structural, design-level issues (e.g. coupling, missing abstractions, scalability constraints, misapplied patterns).
2. **Code Quality** — implementation-level issues (e.g. readability, error handling, duplication, testability) found in the actual file contents above.
3. **Documentation Gaps** — missing, stale, or misleading documentation relative to what the code actually does and what the user's goal requires.

For every finding, provide:
- **Area** — one of Architectural Pattern / Code Quality / Documentation Gap.
- **Issue** — a specific, concrete description of the problem, citing the file(s)/section(s) involved.
- **Rationale** — why this matters specifically for the stated user goal, not in the abstract.
- **Impact/Effort** — classify the finding into one of four ranked groups, per project.md's decision-matrix requirement: "High Impact / Low Effort", "High Impact / High Effort", "Low Impact / Low Effort", or "Low Impact / High Effort".
- **Suggested LLM Action Prompt** — a concrete, ready-to-use prompt an engineer could hand to an LLM coding assistant to implement this specific improvement.

## Output Format
Write your findings as clear prose/markdown, one finding at a time, using the five labeled fields above for each. Do not skip any of the three improvement areas. Do not output JSON — a later step will parse this into structured data. Do not include any other commentary before or after the findings.
PPROMPT
