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

- Related Issue/PR: none; this exception concerns the local daily-close
  repository refactor validation environment, which GitHub cannot reproduce.
- The local `.venv` launcher references an unavailable Python installation.
  Validation uses the desktop bundled Python 3.12, appending the existing
  `.venv/Lib/site-packages` for missing pure-Python dependencies. This is not
  validation of the original Python 3.13 environment.
- Next safe action: validate with a working project Python 3.13 environment
  before PR preparation and remove this exception when the local runtime is
  repaired. No additional files or modules are claimed by this entry.

## Safety invariants

- Never record tokens, account details, cookies, personal data, production
  data, browsing history, or local secrets.
- A handoff entry never expands AI authorization.
- AI must not merge, deploy, change repository settings or secrets, operate on
  production data, approve SEC-4, or declare a public launch.
- Keep ACTUAL, eFortune estimated fallback, formal `76W`, missing data, and
  formal zero semantically distinct.
