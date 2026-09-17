# BigQMT

BigQMT is the verified, recoverable and auditable QMT platform for ETF and A
share strategy execution, accounting and monitoring. It begins with
simulation-first validation and keeps production accounts read-only until the
separate production admission gates are explicitly approved.

The source tree is publishable: account values in committed examples are
synthetic identifiers only. Real QMT credentials, Fact Secrets, execution
keys, machine-local paths and runtime state stay outside Git and are injected
on each host.

## Source and release policy

- GitHub repository `kitling-cax/Bigqmt` is the sole source of code, tests,
  documentation and non-secret configuration templates.
- NAS contains immutable release packages, checksums, sanitized reports and
  backups; it is not a source checkout or execution-authority mechanism.
- `.105` owns integration, `main`, tags and releases. `.125` and `.113` use
  host branches and pull requests after local build/deployment validation.
- A single account can have multiple online QMT terminals but only one
  Coordinator-approved host may become an executor at a time. All others are
  read-only.

## Local setup

Copy `config/machine.local.example.json` to `config/machine.local.json` and
adjust only local directories, host identity and ports. Never commit the local
file, QMT credentials, Fact Secrets, authorization Keys, runtime databases or
broker logs.

```powershell
py -3.12 -m pytest -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_portable_host_bundles.ps1
```

These commands validate source and build artifacts only. They do not grant an
execution lease or permit an order.

See `AGENTS.md` for the project safety constitution and `docs/` for the
Coordinator, Host Agent and deployment contracts.
