---
description: Post-commit self-check — verify the last commit against its spec and this repo's policies, then STOP.
---

Verify the current branch's most recent commit. Execute the checks, report,
then **STOP — no push, no agents, no fixes.**

Report each, concisely, with concrete evidence (counts, pass/fail output,
file:line):

- **(a) Suite** — run `.venv/bin/pytest -q`; report pass/fail counts.
- **(b) DONE command** — if the commit implements a spec in `specs/`, run that
  spec's DONE command and paste its real result. The DONE command is the only
  definition of done; "tests pass" alone does not substitute.
- **(c) Determinism** — name any step this commit adds that could give a
  different answer on a re-run (LLM calls, unpinned versions, time-dependent
  logic, unordered output). Confirm each is justified in DECISIONS.md, or
  flag it.
- **(d) Fixtures** — no commit in this work touches `tests/fixtures/`: on a
  branch check `git diff main...HEAD --stat -- tests/fixtures/`; on main check
  `git diff HEAD~1 --stat -- tests/fixtures/` (skip if HEAD has no parent).
  Must be empty. Also confirm no test was weakened to get green.
- **(e) Divergence** — any spec-vs-reality gap hit during the work: name it
  and confirm it was reported to the user, not silently adapted.
- **(f) Eyeball** — the ONE file you'd most want a human to read
  line-by-line, and why.

This is an explicit, on-request verification. Do not treat its presence as a
cue to run it automatically — it runs only when invoked.
