# Portable Host bundle 0.2.1: Fact Secret path correction

## Defect in 0.2.0

The facts identity generator intentionally rejects a Secret output below its
own project root. Bundle 0.2.0 configured `fact_secret_path` as
`secrets/host-fact.json` inside the portable bundle, so first provisioning
would correctly stop with `refusing to write a fact Secret inside the project
tree`.

This is a security-policy conflict, not a Coordinator or NAS availability
failure. A Bash session on `.125` additionally cannot enumerate a Windows UNC
path with `ls`/`find`; that result must not be used as proof that a Windows SMB
publication is absent.

## Correction

Bundle 0.2.1 is a new immutable candidate path. It changes only the configured
Secret destination:

```text
C:\ProgramData\Kitling\BigQMT\host-facts\host-125-fact-shadow-20260917.json
C:\ProgramData\Kitling\BigQMT\host-facts\host-113-fact-shadow-20260917.json
```

The provisioner creates the file only on its assigned Windows host, applies
restricted NTFS ACLs, and does not print it. The portable package still holds
the EXE, local machine configuration, Outbox and non-secret code; it contains
no `secrets/` directory or Secret file.

## Operational rule

Do not run 0.2.0. `.125` must use the 0.2.1 handoff and package. The Shadow
Coordinator still does not trust a newly generated `.125` Secret; first
delivery can remain pending until a separate, explicitly authorized,
Coordinator trust-enrollment procedure is performed.

All paths remain facts-only and `orders_enabled=false`.
