# Portable BigQMT Host Tray

This is a facts-only Host Agent runtime. One folder contains the tray EXE,
machine configuration, local SQLite WAL Outbox and first-run provisioner. It
has no order, cancel, lease, confirmation, QMT RPC or Redis write path.

## First use on the assigned Windows host

1. Copy the entire assigned folder to the local machine, for example
   `E:\kitling_QMT_work\kitling_bigqmt\BigQMT_Host_125`.
2. Review `machine.local.json`. Its relative `audit_path` expects the native
   BigQMT account tray audit at the adjacent project `runtime_data` directory.
   Change only this path if the account tray uses another local location.
3. Double-click `start_host_tray.cmd`. The first run creates a unique local
   Fact Secret in `C:\ProgramData\Kitling\BigQMT\host-facts\`, locks its ACL
   to SYSTEM, Administrators and the current Windows identity, initializes the
   Outbox, then starts the tray.
4. If the native account tray audit does not yet exist, the Host Agent starts
   in a red “waiting for audit log” state. This is expected and does not grant
   any execution authority. Once the audit appears, use “collect and report
   facts now” in the tray menu.

The Fact Secret under `C:\ProgramData\Kitling\BigQMT\host-facts\` is host-local
identity material. Do not copy it to NAS, another computer, chat, source
control, or a backup that ordinary NAS users can read. For a migration, copy
the package folder only and run first use again; the target receives its own
Fact Secret and must be separately trusted by the Coordinator.
