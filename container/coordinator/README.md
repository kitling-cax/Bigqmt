# BigQMT Coordinator OCI shadow package

This directory is a local build artifact for the `.121:18666` **shadow-only**
Coordinator. It does not deploy anything and cannot enable order writing.

The current `192.0.2.121:18443` systemd service remains authoritative. The
shadow package has a separate bind-mounted state directory, instance lock and
database copy. It must be seeded by SQLite online backup; never copy a live
SQLite/WAL pair by file copy.

Before a future deployment, run the C0-C4 automated tests and generate an
immutable release manifest. Deployment to `.121` and any `18443` cutover each
need their own explicit approval.
