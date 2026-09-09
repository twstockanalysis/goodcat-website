# Caddy gRPC patch maintenance

Related Issue: #128. Baseline: `58d4d79`.

The explicit Caddy build dependency moves from gRPC-Go `v1.83.1` to
`v1.83.2`, following the [upstream patch release](https://github.com/grpc/grpc-go/releases/tag/v1.83.2).
Its required `golang.org/x/net` pin also moves from `v0.57.0` to `v0.58.0`.
The [published module requirements](https://proxy.golang.org/google.golang.org/grpc/@v/v1.83.2.mod)
confirm this dependency; the first CI build reproduced the incompatible old
explicit pin. The x/crypto and x/text pins already satisfy the new x/net module.
The Caddy source commit, Go/Alpine images, remaining module pins, UID/GID,
configuration and network exposure are unchanged.

The deployment regression checks the new exact pin. This is a source-level
guard, not proof of the compiled binary's dependency graph or scan result.
The unchanged Security gate must build both images, validate non-root execution,
check the edge configuration and backend health, and scan both images at the
existing HIGH/CRITICAL threshold. No exclusions or weaker gates are added.

The local environment has no Docker CLI available; container execution and
scanning require current-head GitHub Actions evidence. Local Python regression
alone does not establish successful container validation.

This patch is independent of the expense-source document in PR #125. That PR
must include the reviewed patch through a normal maintainer-controlled base
update before its own current-head gate can validate the changed dependency.
Rerunning an unchanged old pin is not a dependency update.

No financial semantics, databases, running local services or production
deployment are changed. Human security/CODEOWNER approval is required before
merge; AI does not declare the system remediated or ready for public launch.
Reverting restores the earlier pin and may restore the failing scan, so rollback
requires a fresh gate and must not be treated as a safe release automatically.
