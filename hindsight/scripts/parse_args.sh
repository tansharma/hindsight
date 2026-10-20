#!/usr/bin/env bash
# T1 test script: validates the three Hindsight inputs (project_root, file_list,
# user_goal) and echoes the confirmation object described in project.md / prompt.md.
#
# Usage:
#   scripts/parse_args.sh --root <path> --goal "<use case>" [--files "a.py,b.py,..."]
#
# Exit codes:
#   0  inputs valid, confirmation JSON printed to stdout
#   1  a required input is missing or invalid

set -euo pipefail

MAX_FILES=300

root=""
goal=""
files_csv=""

usage() {
  echo "Usage: $0 --root <path> --goal \"<use case>\" [--files \"a.py,b.py,...\"]" >&2
  exit 1
}

missing_value() {
  echo "Error: $1 requires a value." >&2
  usage
}

# Escape a string for use inside a JSON string literal: drop control
# characters JSON can't carry raw, then escape \, ", newline, CR, and tab.
json_escape() {
  local s
  s="$(printf '%s' "$1" | LC_ALL=C tr -d '\001-\010\013\014\016-\037')"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      [[ $# -ge 2 ]] || missing_value "$1"
      root="$2"
      shift 2
      ;;
    --goal)
      [[ $# -ge 2 ]] || missing_value "$1"
      goal="$2"
      shift 2
      ;;
    --files)
      [[ $# -ge 2 ]] || missing_value "$1"
      files_csv="$2"
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

if [[ ! -d "$root" ]]; then
  echo "Error: --root '$root' is not a directory." >&2
  exit 1
fi

if [[ -z "$goal" ]]; then
  echo "Error: --goal <user_goal> is mandatory (Hindsight requires a defining use case/goal)." >&2
  exit 1
fi

# Split the CSV file list into an array, dropping empty entries.
files=()
if [[ -n "$files_csv" ]]; then
  IFS=',' read -ra raw_files <<< "$files_csv"
  for f in "${raw_files[@]}"; do
    trimmed="$(echo "$f" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    [[ -n "$trimmed" ]] && files+=("$trimmed")
  done
fi

file_count=${#files[@]}
if (( file_count > MAX_FILES )); then
  echo "Error: file_list has $file_count entries, exceeding the max of $MAX_FILES." >&2
  exit 1
fi

# Build the JSON array of files.
files_json="["
for i in "${!files[@]}"; do
  files_json+="\"$(json_escape "${files[$i]}")\""
  if (( i < file_count - 1 )); then
    files_json+=","
  fi
done
files_json+="]"

esc_root="$(json_escape "$root")"
esc_goal="$(json_escape "$goal")"

printf '{ "root": "%s", "files": %s, "goal": "%s" }\n' "$esc_root" "$files_json" "$esc_goal"
