"""Pin-pair guard for the secrets floor (phase-7 review ruling 3).

The gitleaks version is pinned twice — GITLEAKS_PIN in
scripts/secrets_audit.sh and the release URL in ci.yml's secrets job —
and drift between them means either spurious local pre-push failures
(the --no-verify pressure) or two layers scanning with different
allowlist-parsing semantics while both report green.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_gitleaks_pin_cannot_drift_between_floor_and_ci() -> None:
    floor = (REPO_ROOT / "scripts" / "secrets_audit.sh").read_text()
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    pin = re.search(r'^GITLEAKS_PIN="([0-9.]+)"$', floor, re.MULTILINE)
    assert pin, "GITLEAKS_PIN not found in scripts/secrets_audit.sh"
    version = pin.group(1)

    # the exact pinned version must appear in CI's download URL and
    # archive name (one string in ci.yml carries both)
    assert (
        f"gitleaks/releases/download/v{version}/gitleaks_{version}_linux_x64.tar.gz"
        in ci
    ), f"ci.yml does not download gitleaks {version} (floor pin)"


def test_every_gitleaks_scan_disables_inline_allows() -> None:
    """Every `gitleaks git` invocation in the floor and the workflow must
    carry --ignore-gitleaks-allow, and both self-governance guard steps
    must be present in ci.yml.

    Known limit, on purpose: a PR controls both scanned files AND this
    test, so this catches accidental drift, not malice — malicious
    workflow edits are the visible-in-diff class, closed by branch
    protection at the public flip (docs/public_flip_checklist.md).
    """
    for rel in ("scripts/secrets_audit.sh", ".github/workflows/ci.yml"):
        text = (REPO_ROOT / rel).read_text().replace("\\\n", " ")
        # ` --` separates real invocations (always flag-bearing here)
        # from the floor's "PASS (d) gitleaks git ." echo labels
        invocations = re.findall(r"gitleaks git \. --[^\n]*", text)
        assert invocations, f"{rel}: no gitleaks git invocation found"
        for inv in invocations:
            assert "--ignore-gitleaks-allow" in inv, (
                f"{rel}: gitleaks invocation missing --ignore-gitleaks-allow: {inv}"
            )

    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    for step in (
        "gitleaks with base-branch config (self-governance guard)",
        "secrets floor with base-branch script (self-governance guard)",
    ):
        assert step in ci, f"ci.yml: guard step missing: {step}"
