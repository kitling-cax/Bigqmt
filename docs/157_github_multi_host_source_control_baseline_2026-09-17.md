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

## Remaining administrator action

In GitHub repository settings, protect `main`: require pull requests and the
`BigQMT source CI` check before merge; disable force push and deletion. `.105`
remains the only integrator/release owner. `.125` and `.113` use the published
onboarding instructions and push only `host/125/*` or `host/113/*` branches.
