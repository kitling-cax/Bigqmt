## Scope

- [ ] Branch is `host/105/*`, `host/125/*`, or `host/113/*`; it is not `main`.
- [ ] This change does not alter production order authority, lease grants or
      Coordinator execution policy without separately documented approval.

## Local evidence

- [ ] `py -3.12 -m pytest -q` passed on the originating Windows host.
- [ ] Relevant local build completed (Host Tray and/or Coordinator image).
- [ ] Deployment evidence, if any, is sanitized and linked below.

## Source hygiene

- [ ] No `machine.local.json`, credentials, Fact Secret, authorization Key,
      QMT data, SQLite/WAL, logs, EXE or release package is included.
- [ ] `.125/.113` changes were tested locally but remain read-only unless the
      Coordinator separately grants a valid executor authorization.

## `.105` integration decision

- [ ] `source-and-tray` is green.
- [ ] `coordinator-container` is green.
- [ ] Reviewed and merged by the `.105` integration owner.

Evidence / rollback note:
