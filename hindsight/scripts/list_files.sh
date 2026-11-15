#!/usr/bin/env bash
# Lists the files Hindsight should review under a project root, one path per
# line (relative to --root, byte-order sorted). Used when the user names only
# a directory, and in non-interactive runs, where nobody can confirm a
# hand-picked list — the same tree always yields the same file_list.
#
# Usage:
#   scripts/list_files.sh --root <path>
#   scripts/list_files.sh --root <path> > files.txt
#   scripts/list_files.sh --root <path> --since <git-ref>
#   scripts/import_graph.py --root <path> --files-from files.txt
#
# Behavior:
#   - In a git work tree, lists tracked plus untracked-but-not-ignored files,
#     so .gitignore is respected; otherwise walks the tree with find.
#   - Always skips common.sh's PRUNE_DIRS (dependency/build dirs and
#     hindsight-history/), Hindsight's own inHindsight.md/.json, symlinks,
#     binary files, and files whose names look like secrets (.env, *.pem,
#     id_rsa, ...), naming each secret skipped on stderr.
#   - Logs a summary line to stderr. Nothing but paths goes to stdout.
#   - --since <git-ref> (a scoped review, references/scoped-review.md):
#     lists only the files that changed between the ref and the working
#     tree (committed, staged, unstaged, or new and untracked) plus their
#     direct dependents from import_graph.py, after the same filtering.
#     Deleted files are not listed. Needs a git work tree and a valid ref.
#
# Exit codes:
#   0  listing printed (possibly empty)
#   1  --root missing or not a directory; with --since, not a git work tree
#      or an unknown ref

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

root=""
since=""

usage() {
  echo "Usage: $0 --root <path> [--since <git-ref>]" >&2
  exit 1
}

missing_value() {
  echo "Error: $1 requires a value." >&2
  usage
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      [[ $# -ge 2 ]] || missing_value "$1"
      root="$2"
      shift 2
      ;;
    --since)
      [[ $# -ge 2 && -n "$2" ]] || missing_value "$1"
      since="$2"
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

cd "$root"

if [[ -n "$since" ]]; then
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Error: --since needs a git work tree; '$root' is not in one." >&2
    exit 1
  fi
  if ! git rev-parse --verify --quiet "${since}^{commit}" >/dev/null; then
    echo "Error: --since '$since' is not a commit, branch, or tag in this repository." >&2
    exit 1
  fi
fi

candidates() {
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git ls-files -z --cached --others --exclude-standard
  else
    local prune=() d
    for d in "${PRUNE_DIRS[@]}"; do
      prune+=(-o -name "$d")
    done
    find . -type d \( "${prune[@]:1}" \) -prune -o -type f -print0
  fi
}

listed=()
binary_count=0
secret_count=0
output_count=0

while IFS= read -r -d '' f; do
  f="${f#./}"
  if [[ "$f" == *$'\n'* ]]; then
    echo "Warning: path contains a newline, skipping." >&2
    continue
  fi
  [[ -f "$f" && ! -L "$f" ]] || continue
  in_pruned_dir "$f" && continue
  if is_hindsight_output "$f"; then
    output_count=$((output_count + 1))
    continue
  fi
  if is_secret_path "$f"; then
    echo "Warning: possible secret, not listed: $f" >&2
    secret_count=$((secret_count + 1))
    continue
  fi
  if is_binary "$f"; then
    binary_count=$((binary_count + 1))
    continue
  fi
  listed+=("$f")
done < <(candidates)

skipped="skipped $binary_count binary, $secret_count possible secret, $output_count Hindsight output"

if [[ -z "$since" ]]; then
  if (( ${#listed[@]} > 0 )); then
    printf '%s\n' "${listed[@]}" | LC_ALL=C sort
  fi
  echo "Listed ${#listed[@]} file(s); $skipped." >&2
  exit 0
fi

# Scoped listing: changed files that survived the filters above, plus the
# listed files that directly import one of them.
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
if (( ${#listed[@]} > 0 )); then
  printf '%s\n' "${listed[@]}" | LC_ALL=C sort > "$tmp/all"
else
  : > "$tmp/all"
fi
{
  git diff --name-only --no-renames --relative -z "$since" -- .
  git ls-files -z --others --exclude-standard
} | tr '\0' '\n' | LC_ALL=C sort -u > "$tmp/diff"
LC_ALL=C comm -12 "$tmp/all" "$tmp/diff" > "$tmp/changed"
python3 "$(dirname "${BASH_SOURCE[0]}")/import_graph.py" --root . --files-from "$tmp/all" \
  --dependents-of "$tmp/changed" > "$tmp/dependents"
LC_ALL=C sort -u "$tmp/changed" "$tmp/dependents"

changed_count=$(wc -l < "$tmp/changed" | tr -d ' ')
dependent_count=$(wc -l < "$tmp/dependents" | tr -d ' ')
echo "Listed $((changed_count + dependent_count)) of ${#listed[@]} file(s): $changed_count changed since $since, $dependent_count direct dependent(s); $skipped." >&2
