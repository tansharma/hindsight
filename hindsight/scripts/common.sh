# Shared helpers for Hindsight's shell scripts (list_files.sh,
# aggregate_context.sh). Sourced, not executed.

BINARY_SNIFF_BYTES=8192

# Directory names never descended into when listing or summarizing a project.
# hindsight-history/ holds Hindsight's own archived reviews.
PRUNE_DIRS=(.git node_modules vendor dist build target .venv venv __pycache__ hindsight-history)

# True if the path is one of Hindsight's own output files (at any depth, so
# a review of a subproject is skipped too). A re-run must not review the
# previous review as if it were project content.
is_hindsight_output() {
  case "$(basename "$1")" in
    inHindsight.md|inHindsight.json) return 0 ;;
  esac
  return 1
}

is_binary() {
  local sniffed stripped
  sniffed=$(head -c "$BINARY_SNIFF_BYTES" "$1" | wc -c | tr -d ' ')
  stripped=$(head -c "$BINARY_SNIFF_BYTES" "$1" | LC_ALL=C tr -d '\000' | wc -c | tr -d ' ')
  [[ "$sniffed" != "$stripped" ]]
}

# True if the path's basename looks like a credential or secret store. Its
# contents are never read into a review, so they can't leak into
# inHindsight.md or into an LLM prompt. Template variants (.env.example,
# .env.sample, ...) are allowed, since they document config without values.
is_secret_path() {
  local name
  name="$(basename "$1")"
  case "$name" in
    .env.example|.env.sample|.env.template|.env.dist) return 1 ;;
    .env|.env.*|*.pem|*.key|*.p12|*.pfx|*.jks|*.keystore) return 0 ;;
    id_rsa|id_rsa.*|id_dsa|id_dsa.*|id_ecdsa|id_ecdsa.*|id_ed25519|id_ed25519.*) return 0 ;;
    .npmrc|.pypirc|.netrc|.git-credentials|*.tfstate|*.tfstate.*) return 0 ;;
    credentials|credentials.json|secrets.json|secrets.yml|secrets.yaml) return 0 ;;
  esac
  return 1
}

# True if a root-relative path lies inside one of PRUNE_DIRS.
in_pruned_dir() {
  local d
  for d in "${PRUNE_DIRS[@]}"; do
    [[ "/$1" == */"$d"/* ]] && return 0
  done
  return 1
}

# Fill the global array `files` from a comma-separated list ($1) or, if $2
# is non-empty, from a newline-delimited file ("-" for stdin). Surrounding
# whitespace (including a CRLF's CR) and blank entries are dropped.
read_file_list() {
  local csv="$1" from="$2" entry trimmed
  local -a raw=()
  files=()
  if [[ -n "$from" ]]; then
    if [[ "$from" == "-" ]]; then
      while IFS= read -r entry || [[ -n "$entry" ]]; do raw+=("$entry"); done
    else
      while IFS= read -r entry || [[ -n "$entry" ]]; do raw+=("$entry"); done < "$from"
    fi
  elif [[ -n "$csv" ]]; then
    IFS=',' read -ra raw <<< "$csv"
  fi
  for entry in ${raw[@]+"${raw[@]}"}; do
    trimmed="$(printf '%s' "$entry" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    [[ -n "$trimmed" ]] && files+=("$trimmed")
  done
  return 0
}
