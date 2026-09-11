# AI handoff

This file is an exception log for collaboration facts that cannot be recovered
from GitHub and the current Git worktree. It is not a live status dashboard.

Issues and PRs are the source of truth for requirements, ownership, discussion,
review, CI, approval, and merge state. Git is the source of truth for branches,
commits, worktrees, and uncommitted changes. Always refresh and inspect those
sources directly before starting or resuming work.

## Required live verification

Use the relevant commands instead of relying on a status copied into this file:

```powershell
git fetch origin
git status --short --branch
git branch --show-current
gh repo view --json defaultBranchRef
gh issue view <number> --json state,title,url,body
gh pr view <number> --json state,isDraft,baseRefName,headRefName,mergeStateStatus,statusCheckRollup,reviews,url
```

Also inspect the current Issue and PR discussion when decisions or unresolved
comments may affect the task. A prior chat summary or handoff entry never proves
that a branch was pushed, a PR was approved, CI passed, or a change was merged.

## When an entry is required

Add a short entry only when a successor needs material context that GitHub and
Git cannot provide, for example:

- uncommitted work that cannot yet be committed or pushed;
- local-only artifacts, test fixtures, or reproducible commands needed to
  continue safely;
- a non-public blocker or external dependency that is not appropriate for a
  public Issue or PR;
- claimed files or modules that are not already recorded on GitHub and could
  conflict with another active worktree.

Each exception entry must state why GitHub and Git are insufficient, identify
the related Issue or PR, describe the local-only state without exposing private
data, list any claimed files, and give the next safe action. Remove an entry
after its material facts become recoverable from GitHub or Git.

## Do not record transient GitHub state

Do not add or update this file merely to record:

- waiting for review, approval, a decision, CI, or merge;
- Draft, ready-for-review, closed, or merged status;
- the current approval count, reviewer assignment, or check result;
- whether a branch is current with or behind its base;
- the latest default-branch commit or a PR's latest commit;
- completed-work summaries, test evidence, or decisions already present in an
  Issue, PR, commit, or tracked project document.

Ordinary pauses, review transitions, new CI runs, approvals, and merges require
no `AI_HANDOFF.md` edit. Collaborators must verify those states live.

## Current repository-only exceptions

### Local validation runtime

- Related Issue: #109. This exception records the local runtime location.

- The original `.venv` launcher references an unavailable Python installation.
  With owner authorization, an independent ignored `venv/` was created using
  the desktop bundled Python 3.12 and `requirements.lock` dependencies.
- Use `venv/Scripts/python.exe` for local validation. This environment is
  separate from the original Python 3.13 `.venv`; do not overlay its packages.
- Remove this exception once the standard project runtime is repaired.

### Local annual-expense candidate artifacts

- Related Issue: #130. Databases, source PDF and audit JSON are intentionally
  ignored and cannot be recovered from GitHub/Git.
- In the `goodcat-expense-import` worktree, the candidate is
  `database/v5-3d-expense-20260906.db` (SHA-256
  `21fef06fdce269a04a1afa205ee7a1f5e734f2ded25d5879e23f29b52ccb320d`).
- Its source is the sibling `goodcat-v5-nomura` worktree's
  `database/v5-3d-nomura-20260906.db`. The reviewed PDF is in sibling
  `goodcat-v5-expense/data/processed/expense-124/0056-prospectus.pdf`.
- Local baseline/candidate audit JSON and test logs are under this worktree's
  `data/processed/expense-*`. These artifacts contain no authority to switch
  services or write production data. Reverify hashes before any later use;
  see `docs/ANNUAL_EXPENSE_CONTRACT.md` for reproduction and constraints.

### Local non-distribution candidate

- Related Issue: #133. The ignored candidate in the `goodcat-non-distribution`
  worktree is `database/v5-3d-non-distribution-20260906.db`, SHA-256
  `1c52c0edd0d0ad644f07e427c3e10d6a33e222f9b650f50b7c403845b951250e`.
- Its source is the annual-expense candidate recorded above. No live service
  was switched. Reverify hashes and the non-distribution contract before using
  these local-only artifacts; no production operation is authorized.
- The local audit is `data/processed/non-distribution-audit.json`; root-level
  `non-distribution-*.log` files are ignored diagnostic outputs. GitHub/Git
  cannot recover those files; rerun the documented read-only audit if absent.

### Local V5-4 balance replay artifacts

- Related Issue: #135. The `goodcat-v5-balance` worktree retains ignored
  `data/processed/balance-audit.json`, `balance-alternatives.log`,
  `balance-audit.log` and `balance-full.log`; GitHub/Git cannot recover them.
- The replay reads the #133 immutable candidate described above at 2026-09-06.
  No new database is created. Reverify the candidate hash before reuse; rerun
  `deployment.v5_full_database_audit` if the audit artifact is absent.

### Local objective-search validation artifacts

- Related Issue: #137. The `goodcat-v5-objectives` worktree retains ignored
  `data/processed/objectives-final-audit.json`, `objectives-final-audit.log`
  (including `STRATEGY` lines for each of the eight ordered cases), and
  `objectives-full-final.log`. GitHub/Git cannot recover these local artifacts.
- The replay reads the #133 immutable candidate at 2026-09-06. Reverify its
  recorded hash before reuse. Reproduce via `deployment.v5_full_database_audit`;
  obtain complete strategy results with `build_allocation_results` for its
  `build_audit_cases`. No production or service change is authorized.
- Non-final `objectives-full.log` and `objectives-audit.log` are interrupted
  exploratory runs before the Pareto-performance correction, not final evidence.

### Local capital-ceiling replay artifacts

- Related Issue: #139. Ignored artifacts in `goodcat-v5-capital-cap` are
  `data/processed/cap-unlimited-audit.json`, `cap-unlimited-audit.log`,
  `cap-scenarios.log` and `cap-full.log`. GitHub/Git cannot recover these files.
- Both replays read the #133 immutable candidate at 2026-09-06; no new database
  is created. Reverify its recorded hash before reuse. Reproduce the unlimited
  run with `deployment.v5_full_database_audit`; use its eight `build_audit_cases`
  with `build_allocation_results` and the test caps in the algorithm contract
  for the capped run. These are not product-default caps or service-switch authority.

## Safety invariants

- Never record tokens, account details, cookies, personal data, production
  data, browsing history, or local secrets.
- A handoff entry never expands AI authorization.
- AI must not merge, deploy, change repository settings or secrets, operate on
  production data, approve SEC-4, or declare a public launch.
- Keep ACTUAL, eFortune estimated fallback, formal `76W`, missing data, and
  formal zero semantically distinct.
