#!/usr/bin/env bash
# Deterministic pre-push secrets floor. Six mechanical checks; PASS/FAIL per
# check, non-zero exit on any failure. The security-reviewer agent runs this
# FIRST, then applies judgment on top — this script is the floor, not the audit.
set -u
cd "$(git rev-parse --show-toplevel)"

fail=0

check_empty() { # $1 label, $2 offending output (empty = pass)
  if [ -z "$2" ]; then
    echo "PASS  $1"
  else
    echo "FAIL  $1"
    printf '%s\n' "$2" | sed 's/^/      /'
    fail=1
  fi
}

# (a) env files (.env, .env.*, .envrc*, *.env) never tracked — current index
# and full history, case-insensitive. The ROOT .env.example is the one
# sanctioned exception (root-only, matching the .gitignore negation; a
# nested copy fails here): bare keys, no values — asserted by check (f).
env_hits=$( { git ls-files; git log --all --pretty=format: --name-only --diff-filter=A; } \
  | grep -iE '(^|/)\.env(rc)?(\..+)?$|(^|/)[^/]+\.env$' \
  | grep -ivE '^\.env\.example$' | sort -u || true)
check_empty "(a) env files (.env* / .envrc* / *.env) never tracked (index + full history)" "$env_hits"

# (b) no data/ or *.duckdb tracked
data_hits=$(git ls-files | grep -E '^data/|\.duckdb$' || true)
check_empty "(b) no data/ or *.duckdb tracked" "$data_hits"

# (e) no terraform state, tfvars, or .terraform/ ever tracked — current
# index and full history. State and tfvars can hold cleartext resource
# values (external ids, account ids); .gitignore alone is one layer.
tf_hits=$( { git ls-files; git log --all --pretty=format: --name-only --diff-filter=A; } \
  | grep -E '\.tfstate(\.|$)|\.tfvars(\.json)?$|(^|/)\.terraform/' | sort -u || true)
check_empty "(e) no *.tfstate / *.tfvars / .terraform ever tracked (index + full history)" "$tf_hits"

# (f) .env.example is the one sanctioned env file (check a's root-only
# exception): every non-comment, non-blank line must be a bare KEY= —
# no values. Reads the INDEX content (git show :.env.example), not the
# working tree — what would ship is what is checked — and absence from
# the index (deleted, renamed, never staged) is itself a FAIL, or the
# check could be bypassed silently. Offenders reported by line number
# only, never content (a value here must never be echoed into logs).
if envex_content=$(git show :.env.example 2>/dev/null); then
  envex_hits=$(printf '%s\n' "$envex_content" \
    | grep -nvE '^[[:space:]]*(#|$)' \
    | grep -vE '^[0-9]+:[A-Za-z_][A-Za-z0-9_]*=$' \
    | cut -d: -f1 | sed 's/^/.env.example line /' || true)
  check_empty "(f) .env.example (index) holds bare keys only (KEY=, no values)" "$envex_hits"
else
  echo "FAIL  (f) .env.example absent from the git index — the sanctioned example file must exist at the repo root with bare keys only"
  fail=1
fi

# (c) known secret shapes across all history (-l: report commit:path, never the value)
# own path excluded: the pattern literals below would otherwise self-match
grep_hits=$(git grep -I -l -E \
  'sk-ant-|AKIA[A-Z0-9]{16}|BEGIN (RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY' \
  $(git rev-list --all) -- ':!scripts/secrets_audit.sh' 2>/dev/null || true)
check_empty "(c) git grep over rev-list --all (sk-ant- / AKIA / private keys)" "$grep_hits"

# (d) gitleaks over full git history (--redact: report findings, never the
# value). Version pinned to CI's binary (ci.yml secrets job): older gitleaks
# parses [[allowlists]]/condition differently, silently changing what a
# green scan means — a mismatched binary FAILS instead of scanning.
GITLEAKS_PIN="8.30.1"
if command -v gitleaks >/dev/null 2>&1; then
  gitleaks_ver=$(gitleaks version 2>/dev/null || true)
  gitleaks_ver=${gitleaks_ver#v}
  if [ "$gitleaks_ver" != "$GITLEAKS_PIN" ]; then
    echo "FAIL  (d) gitleaks $gitleaks_ver != pinned $GITLEAKS_PIN (ci.yml pin) — align the binary or update both pins together"
    fail=1
  elif gitleaks_out=$(gitleaks git . --redact --no-banner --verbose 2>&1); then
    echo "PASS  (d) gitleaks git ."
  else
    echo "FAIL  (d) gitleaks git ."
    printf '%s\n' "$gitleaks_out" | sed 's/^/      /'
    fail=1
  fi
else
  echo "FAIL  (d) gitleaks git . — gitleaks not installed (brew install gitleaks)"
  fail=1
fi

exit "$fail"
