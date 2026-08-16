#!/usr/bin/env bash
# Deterministic pre-push secrets floor. Seven mechanical checks; PASS/FAIL per
# check, non-zero exit on any failure. The security-reviewer agent runs this
# FIRST, then applies judgment on top — this script is the floor, not the audit.
set -u
cd "$(git rev-parse --show-toplevel)"

# --skip-gitleaks skips ONLY check (d). Argv on purpose, not an env var
# (2026-08-16 ruling): ambient environment cannot inject arguments, so
# the fail-open class — any shell or workflow scope exporting a flag —
# is removed rather than narrowed. Sole legitimate caller: ci.yml's
# base-script guard (pin-bump deadlock; see the GITLEAKS_PIN comment).
skip_gitleaks=0
if [ "${1:-}" = "--skip-gitleaks" ]; then
  skip_gitleaks=1
fi

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
  | grep -vE '^\.env\.example$' | sort -u || true)
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
  # two scans: non-comment lines must be bare KEY=; comment lines are
  # exempt from that rule, so any KEY=<nonempty> shape INSIDE a comment
  # fails too (a value must not hide behind a #). Shape-based on
  # purpose — non-"=" prose in comments is (c)/(d)'s layer.
  envex_hits=$( { printf '%s\n' "$envex_content" \
      | grep -nvE '^[[:space:]]*(#|$)' \
      | grep -vE '^[0-9]+:[A-Za-z_][A-Za-z0-9_]*=$'; \
    printf '%s\n' "$envex_content" \
      | grep -nE '^[[:space:]]*#' \
      | grep -E '[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]'; } \
    | cut -d: -f1 | sort -nu | sed 's/^/.env.example line /' || true)
  check_empty "(f) .env.example (index) holds bare keys only (KEY=, no values)" "$envex_hits"
else
  echo "FAIL  (f) .env.example absent from the git index — the sanctioned example file must exist at the repo root with bare keys only"
  fail=1
fi

# (g) no .gitleaksignore at either boundary where it can act: the git
# index (a PR can only ship tracked files) or the working tree, even
# untracked (a local copy still mutes a local scan). Asymmetry is
# deliberate: the worktree half is root-only/case-exact because that
# is the only name and location gitleaks itself reads; the index half
# stays any-depth/-i as cheap hygiene. History is NOT
# scanned — deliberately: gitleaks reads the file from the checkout at
# scan time, so a deleted historical copy cannot mute any scan and
# history coverage would guard a non-mechanism (2026-08-15 ruling;
# forensic record of the one historical copy in DECISIONS.md).
# .gitleaks.toml is the ONE sanctioned exception channel because it is
# the only CI-guarded one.
gli_hits=$( { git ls-files | grep -iE '(^|/)\.gitleaksignore$'; \
  [ -e .gitleaksignore ] && echo ".gitleaksignore (working tree)"; } | sort -u || true)
check_empty "(g) no .gitleaksignore in the index or working tree" "$gli_hits"

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
# Bump procedure: GITLEAKS_PIN here, the download URL, and the sha256 in
# ci.yml's secrets job move together in ONE PR — the pin-pair test
# (tests/test_secrets_floor.py) enforces the first two mechanically.
# The --skip-gitleaks argv flag skips ONLY this check (CI's base-script
# guard passes it: the base script's old pin would otherwise deadlock any
# version bump); every other check still gates the exit code.
GITLEAKS_PIN="8.30.1"
if [ "$skip_gitleaks" = "1" ]; then
  echo "SKIP  (d) gitleaks (--skip-gitleaks — base-script guard)"
elif command -v gitleaks >/dev/null 2>&1; then
  gitleaks_ver=$(gitleaks version 2>/dev/null || true)
  gitleaks_ver=${gitleaks_ver#v}
  # inline "gitleaks:allow" comments are ignored (probe-proven). The
  # ignore-file channel is closed by check (g), not by flags:
  # --gitleaks-ignore-path probed inert against a repo-root
  # .gitleaksignore on the pinned 8.30.1 (2026-08-15).
  # .gitleaks.toml stays the one sanctioned exception channel.
  if [ "$gitleaks_ver" != "$GITLEAKS_PIN" ]; then
    echo "FAIL  (d) gitleaks $gitleaks_ver != pinned $GITLEAKS_PIN (ci.yml pin) — align the binary or update both pins together"
    fail=1
  elif gitleaks_out=$(gitleaks git . --redact --no-banner --verbose \
      --ignore-gitleaks-allow 2>&1); then
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
