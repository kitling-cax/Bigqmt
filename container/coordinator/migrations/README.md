# Coordinator PostgreSQL migrations

These SQL files are versioned design artifacts for the future PostgreSQL
Coordinator database. They are not executed automatically by the current
18443 systemd service or the 18666 shadow container.

Before applying a migration:

1. Provision a separate PostgreSQL database or disposable container.
2. Calculate the exact file SHA-256 and record it in `schema_migrations`.
3. Apply the migration with a transaction and run the migration tests.
4. Replay representative Host Agent facts and verify idempotency.
5. Perform a restore test from the resulting backup.
6. Obtain a separate approval before connecting any production endpoint.

The current Coordinator continues to use its existing SQLite state. The
PostgreSQL schema is a future control/ledger target; it is not a live order
path and it must not receive QMT credentials, authorization keys, or Redis
passwords.
