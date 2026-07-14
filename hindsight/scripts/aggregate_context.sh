#!/usr/bin/env bash
# T2 test script: reads every file in file_list into memory and concatenates
# them into a single demarcated context buffer, preceded by a high-level
# directory structure summary. Mirrors the --root/--files contract established
# by scripts/parse_args.sh (T1) so the two can be chained.
#
# Usage:
#   scripts/aggregate_context.sh --root <path> --files "a.py,b.py,..."
#
# Behavior:
#   - Files are resolved relative to --root (absolute paths are used as-is).
#   - Missing files are skipped with a warning on stderr; they do not abort
#     the run, since one unreadable file shouldn't block the whole review.
#   - Logs a summary line to stderr: files read / missing / total bytes.
#   - Prints the directory structure summary + concatenated file contents to
#     stdout, ready to feed into T3's prompt assembly.
#
# Exit codes:
#   0  ran to completion (even if some files were missing)
#   1  a required input is missing (--root or --files)

set -euo pipefail

root=""
files_csv=""

usage() {
  echo "Usage: $0 --root <path> --files \"a.py,b.py,...\"" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      root="${2:-}"
      shift 2
      ;;
    --files)
      files_csv="${2:-}"
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

if [[ -z "$files_csv" ]]; then
  echo "Error: --files \"a.py,b.py,...\" is required." >&2
  exit 1
fi

if [[ ! -d "$root" ]]; then
  echo "Error: --root '$root' is not a directory." >&2
  exit 1
fi

IFS=',' read -ra raw_files <<< "$files_csv"
files=()
for f in "${raw_files[@]}"; do
  trimmed="$(echo "$f" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  [[ -n "$trimmed" ]] && files+=("$trimmed")
done

# --- Directory structure summary -------------------------------------------
echo "--- DIRECTORY STRUCTURE: $root ---"
( cd "$root" && find . -maxdepth 3 \( -path '*/.git' -o -path '*/.git/*' \) -prune -o -print | sed -e 's|^\./||' -e '/^\.$/d' | sort )
echo

# --- File contents -----------------------------------------------------------
read_count=0
missing_count=0
total_bytes=0

for f in "${files[@]}"; do
  if [[ "$f" = /* ]]; then
    path="$f"
  else
    path="$root/$f"
  fi

  if [[ ! -f "$path" ]]; then
    echo "Warning: file not found, skipping: $f" >&2
    missing_count=$((missing_count + 1))
    continue
  fi

  echo "--- FILE: $f ---"
  cat "$path"
  echo
  read_count=$((read_count + 1))
  bytes=$(wc -c < "$path" | tr -d ' ')
  total_bytes=$((total_bytes + bytes))
done

echo "Read $read_count file(s), $missing_count missing, $total_bytes total bytes." >&2
