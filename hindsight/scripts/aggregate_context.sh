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
#   - Files are resolved relative to --root (absolute paths are accepted only
#     if they resolve inside --root; symlinks are followed before checking).
#   - Missing files, files outside --root, and binary files (NUL byte in the
#     first 8 KiB) are skipped with a warning on stderr; they do not abort
#     the run, since one unreadable file shouldn't block the whole review.
#   - Files larger than HINDSIGHT_MAX_FILE_BYTES (default 262144) are
#     truncated to that size, with a visible marker in the output.
#   - The directory summary prunes .git and common dependency/build dirs
#     (node_modules, vendor, dist, build, target, .venv, venv, __pycache__).
#   - Logs a summary line to stderr: files read / missing / skipped /
#     truncated / total bytes.
#   - Prints the directory structure summary + concatenated file contents to
#     stdout, ready to feed into T3's prompt assembly.
#
# Exit codes:
#   0  ran to completion (even if some files were missing)
#   1  a required input is missing (--root or --files)

set -euo pipefail

MAX_FILE_BYTES="${HINDSIGHT_MAX_FILE_BYTES:-262144}"
BINARY_SNIFF_BYTES=8192

root=""
files_csv=""

usage() {
  echo "Usage: $0 --root <path> --files \"a.py,b.py,...\"" >&2
  exit 1
}

missing_value() {
  echo "Error: $1 requires a value." >&2
  usage
}

# Print the physical path of an existing file, following symlinks.
resolve_file() {
  local p="$1" target hops=0
  while [[ -L "$p" && $hops -lt 40 ]]; do
    target="$(readlink "$p")"
    if [[ "$target" = /* ]]; then
      p="$target"
    else
      p="$(dirname "$p")/$target"
    fi
    hops=$((hops + 1))
  done
  printf '%s/%s\n' "$(cd "$(dirname "$p")" && pwd -P)" "$(basename "$p")"
}

is_binary() {
  local sniffed stripped
  sniffed=$(head -c "$BINARY_SNIFF_BYTES" "$1" | wc -c | tr -d ' ')
  stripped=$(head -c "$BINARY_SNIFF_BYTES" "$1" | LC_ALL=C tr -d '\000' | wc -c | tr -d ' ')
  [[ "$sniffed" != "$stripped" ]]
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      [[ $# -ge 2 ]] || missing_value "$1"
      root="$2"
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

if [[ -z "$files_csv" ]]; then
  echo "Error: --files \"a.py,b.py,...\" is required." >&2
  exit 1
fi

if [[ ! -d "$root" ]]; then
  echo "Error: --root '$root' is not a directory." >&2
  exit 1
fi

if ! [[ "$MAX_FILE_BYTES" =~ ^[0-9]+$ ]] || (( MAX_FILE_BYTES == 0 )); then
  echo "Error: HINDSIGHT_MAX_FILE_BYTES must be a positive integer." >&2
  exit 1
fi

root_abs="$(cd "$root" && pwd -P)"

IFS=',' read -ra raw_files <<< "$files_csv"
files=()
for f in "${raw_files[@]}"; do
  trimmed="$(echo "$f" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  [[ -n "$trimmed" ]] && files+=("$trimmed")
done

# --- Directory structure summary -------------------------------------------
echo "--- DIRECTORY STRUCTURE: $root ---"
( cd "$root" && find . -maxdepth 3 \
    -type d \( -name .git -o -name node_modules -o -name vendor -o -name dist -o -name build \
       -o -name target -o -name .venv -o -name venv -o -name __pycache__ \) -prune \
    -o -print | sed -e 's|^\./||' -e '/^\.$/d' | sort )
echo

# --- File contents -----------------------------------------------------------
read_count=0
missing_count=0
outside_count=0
binary_count=0
truncated_count=0
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

  real="$(resolve_file "$path")"
  case "$real" in
    "$root_abs"/*) ;;
    *)
      echo "Warning: file is outside --root, skipping: $f" >&2
      outside_count=$((outside_count + 1))
      continue
      ;;
  esac

  if is_binary "$real"; then
    echo "Warning: binary file, skipping: $f" >&2
    binary_count=$((binary_count + 1))
    continue
  fi

  bytes=$(wc -c < "$real" | tr -d ' ')
  echo "--- FILE: $f ---"
  if (( bytes > MAX_FILE_BYTES )); then
    head -c "$MAX_FILE_BYTES" "$real"
    echo
    echo "[... truncated by Hindsight: showed $MAX_FILE_BYTES of $bytes bytes ...]"
    echo "Warning: file larger than $MAX_FILE_BYTES bytes, truncated: $f" >&2
    truncated_count=$((truncated_count + 1))
    bytes=$MAX_FILE_BYTES
  else
    cat "$real"
    echo
  fi
  read_count=$((read_count + 1))
  total_bytes=$((total_bytes + bytes))
done

echo "Read $read_count file(s), $missing_count missing, $((outside_count + binary_count)) skipped ($outside_count outside root, $binary_count binary), $truncated_count truncated, $total_bytes total bytes." >&2
