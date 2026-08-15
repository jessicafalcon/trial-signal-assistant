#!/usr/bin/env bash
# Deterministic pre-push secrets floor. Five mechanical checks; PASS/FAIL per
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
# and full history, case-insensitive. .env.example is the one sanctioned
# exception: bare keys, no values.
env_hits=$( { git ls-files; git log --all --pretty=format: --name-only --diff-filter=A; } \
  | grep -iE '(^|/)\.env(rc)?(\..+)?$|(^|/)[^/]+\.env$' \
  | grep -ivE '(^|/)\.env\.example$' | sort -u || true)
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

# (c) known secret shapes across all history (-l: report commit:path, never the value)
# own path excluded: the pattern literals below would otherwise self-match
grep_hits=$(git grep -I -l -E \
  'sk-ant-|AKIA[A-Z0-9]{16}|BEGIN (RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY' \
  $(git rev-list --all) -- ':!scripts/secrets_audit.sh' 2>/dev/null || true)
check_empty "(c) git grep over rev-list --all (sk-ant- / AKIA / private keys)" "$grep_hits"

# (d) gitleaks over full git history (--redact: report findings, never the value)
if command -v gitleaks >/dev/null 2>&1; then
  if gitleaks_out=$(gitleaks git . --redact --no-banner --verbose 2>&1); then
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
