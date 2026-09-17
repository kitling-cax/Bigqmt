# Security and public-source policy

BigQMT source is designed to be publishable without publishing brokerage
credentials or execution authorization. The public repository contains code,
schemas, synthetic account identifiers, example configuration and tests only.

Never commit QMT or broker passwords, Fact Secrets, execution authorization
Keys, API tokens, private keys, `config/machine.local.json`, runtime databases,
WAL files, logs, live reports or complete account statements.

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
