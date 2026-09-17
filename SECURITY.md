# Security and public-source policy

BigQMT source is designed to be publishable without publishing brokerage
credentials or execution authorization. The public repository contains code,
schemas, synthetic account identifiers, example configuration and tests only.

Never commit QMT or broker passwords, Fact Secrets, execution authorization
Keys, API tokens, private keys, `config/machine.local.json`, runtime databases,
WAL files, logs, live reports or complete account statements.

An optional NAS private overlay may provide account identifiers, Coordinator
endpoints, QMT roots and local ports. It is selected by the ignored
`private_config.file` setting or `BIGQMT_PRIVATE_CONFIG_FILE`. The loader rejects
secret-like fields and can require `BIGQMT_PRIVATE_CONFIG_SHA256`. The NAS file
must be read-only for runtime hosts and must never contain passwords, tokens,
Fact Secrets or execution Keys.

Use the ignored local configuration and host-local protected secret store:

```text
config/machine.local.json
C:\ProgramData\Kitling\BigQMT\host-facts\
```

If a credential is ever committed, deleting the file is not sufficient. Revoke
and rotate it, then remove the exposed object from Git history before publishing.

Run the public-source gate before pushing:

```powershell
py -3.12 scripts/check_public_safety.py
py -3.12 -m pytest -q
```
