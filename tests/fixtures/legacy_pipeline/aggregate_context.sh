#!/usr/bin/env bash
# Legacy pipeline (retired from the shipped skill; kept in
# tests/fixtures/legacy_pipeline/ as tested reference code): reads every
# file in file_list into one demarcated context buffer, preceded by a
# high-level directory structure summary, for build_prompt.sh. The live
# skill has the agent read the files itself. Mirrors parse_args.sh's
# --root/--files contract so the two can be chained.
#
# Usage:
#   aggregate_context.sh --root <path> --files "a.py,b.py,..."
#   aggregate_context.sh --root <path> --files-from <list.txt | ->
#
# --files-from reads one path per line ("-" for stdin), e.g. the output of
# hindsight/scripts/list_files.sh; use it for paths that contain commas.
#
# Behavior:
#   - Files are resolved relative to --root (absolute paths are accepted only
#     if they resolve inside --root; symlinks are followed before checking).
#   - Missing files, files outside --root, files whose names look like
#     secrets (.env, *.pem, id_rsa, ... — see common.sh), and binary files
#     (NUL byte in the first 8 KiB) are skipped with a warning on stderr;
#     they do not abort the run, since one unreadable file shouldn't block
#     the whole review.
#   - Files larger than HINDSIGHT_MAX_FILE_BYTES (default 262144) are
#     truncated to that size, with a visible marker in the output.
#   - The directory summary prunes common.sh's PRUNE_DIRS (.git and common
#     dependency/build dirs).
#   - Logs a summary line to stderr: files read / missing / skipped /
#     truncated / total bytes.
#   - Prints the directory structure summary + concatenated file contents to
#     stdout, ready to feed into build_prompt.sh.
#
# Exit codes:
#   0  ran to completion (even if some files were missing)
#   1  a required input is missing (--root, or --files / --files-from)

set -euo pipefail

# Shared helpers live with the shipped scripts.
source "$(dirname "${BASH_SOURCE[0]}")/../../../hindsight/scripts/common.sh"

MAX_FILE_BYTES="${HINDSIGHT_MAX_FILE_BYTES:-262144}"

root=""
files_csv=""
files_from=""

usage() {
  echo "Usage: $0 --root <path> (--files \"a.py,b.py,...\" | --files-from <file|->)" >&2
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
    --files-from)
      [[ $# -ge 2 ]] || missing_value "$1"
      files_from="$2"
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

if [[ -z "$files_csv" && -z "$files_from" ]]; then
  echo "Error: --files \"a.py,b.py,...\" or --files-from <file|-> is required." >&2
  exit 1
fi

if [[ -n "$files_from" && "$files_from" != "-" && ! -r "$files_from" ]]; then
  echo "Error: --files-from '$files_from' not found or not readable." >&2
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

read_file_list "$files_csv" "$files_from"

# --- Directory structure summary -------------------------------------------
prune=()
for d in "${PRUNE_DIRS[@]}"; do
  prune+=(-o -name "$d")
done
echo "--- DIRECTORY STRUCTURE: $root ---"
( cd "$root" && find . -maxdepth 3 -type d \( "${prune[@]:1}" \) -prune \
    -o -print | sed -e 's|^\./||' -e '/^\.$/d' | sort )
echo

# --- File contents -----------------------------------------------------------
read_count=0
missing_count=0
outside_count=0
secret_count=0
binary_count=0
truncated_count=0
total_bytes=0

for f in ${files[@]+"${files[@]}"}; do
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

  if is_secret_path "$f" || is_secret_path "$real"; then
    echo "Warning: possible secret, not read: $f" >&2
    secret_count=$((secret_count + 1))
    continue
  fi

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

echo "Read $read_count file(s), $missing_count missing, $((outside_count + secret_count + binary_count)) skipped ($outside_count outside root, $secret_count possible secret, $binary_count binary), $truncated_count truncated, $total_bytes total bytes." >&2
