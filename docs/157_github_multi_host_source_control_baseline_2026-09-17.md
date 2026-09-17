# GitHub multi-host source-control baseline

## Completed on `.105`

The former non-Git project root is now a Git worktree connected to
`https://github.com/kitling-cax/Bigqmt.git`.

| Commit | Purpose |
|---|---|
| `8356e02a7f3eec3bd232811723708964e74e3025` | Initial reviewed source baseline (534 files) |
| `988cdd5` | GitHub Actions source/container CI and `.125/.113` onboarding |

The remote `main` branch was created successfully and tracks the `.105`
worktree. The baseline includes source, tests, Coordinator container assets,
documentation, progress records and non-secret machine templates. It excludes
machine-local config, credentials, Fact Secrets, authorization Keys, runtime
data, databases/WAL, broker logs, generated EXEs and NAS release packages.

## Verification

- known local SSH-password literal scan of staged source: clean;
- forbidden tracked paths (machine local config, runtime data, secrets,
  SQLite/WAL, EXE/DLL): clean;
- files larger than 5 MB: none;
- portable facts-only Host Tray build: passed;
- existing Python regression suite: 268 test cases exercised successfully
  before baseline publication.

The initial historical document import has 94 pre-existing whitespace findings.
They are not runtime defects and were deliberately not mass-rewritten as part
of the source-control baseline.

## Coordinator container relationship

The same tag/commit contains `container/coordinator/`, its Dockerfile and
Shadow/production templates. CI builds the Coordinator image only; it neither
connects to `.121`, deploys a container, writes a lease nor permits an order.
Container secrets, state volumes, database/WAL and `.121` environment files
remain local and excluded from Git.

## CI result and branch-protection limitation

GitHub Actions run `35221983165` for commit `ed9b07f` completed successfully:
both `source-and-tray` and `coordinator-container` passed. The initial CI
failures revealed missing source-only dependencies and an implicit dependency
on local compiled Tray EXEs; both were corrected without committing binaries.

The repository is private and the current GitHub plan rejects Branch Protection
and Rulesets for private repositories (`403: Upgrade to GitHub Pro or make this
repository public`). Therefore `main` is **not platform-enforced** yet. Keep
the repository private: it contains trading architecture and operational
documentation and must not be made public merely to obtain a free protection
feature.

Until GitHub Pro/Team is explicitly enabled, the operational gate is manual:
only `.105` may push or merge `main`; `.125/.113` push only `host/125/*` or
`host/113/*` and submit a PR. Before `.105` merges, both named CI checks must
be green and the PR template must be complete. After an eligible plan upgrade,
configure `main` to require PRs, `source-and-tray`,
`coordinator-container`, conversation resolution, no force push and no
deletion.
