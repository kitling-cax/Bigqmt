# Portable Host bundle 0.2.0

## Delivered layout

Two deliberately separate folders are built from the same facts-only code:

```text
BigQMT_Host_125/                 # host_id 192.0.2.125
  BigQMT_HostTray.exe            # one Host Agent tray process
  machine.local.json             # target-specific, relative local paths
  start_host_tray.cmd            # first-use launcher
  provision_and_start.ps1        # creates local identity and local state
  secrets/                       # created locally; never publish its contents
  state/simulation/              # local SQLite WAL Outbox
  logs/                          # local Host Agent log
  scripts/ and src/              # self-contained facts-only collector/uploader

BigQMT_Host_113/                 # equivalent bundle for host_id 198.51.100.113
```

`machine.local.json` carries only host identity, audit location, local Outbox
location and the Shadow facts endpoint `http://192.0.2.121:18666`. It has
`orders_enabled: false`; the executable contains no order, lease, confirmation,
QMT RPC or Redis write command.

## First-run and migration rules

The provisioner generates `secrets/host-fact.json` only after the folder is on
the target Windows machine and protects it using local NTFS ACLs. It is not in
the release, NAS publication or a cross-host copy. A copied folder is migrated
without `secrets/`; the new machine generates a different identity and requires
explicit Coordinator trust before its facts can be accepted.

The Host Agent reads the existing native account-tray audit. It does not start
or automate QMT. If audit output is absent, it still launches in a visible
waiting state rather than creating fabricated operating evidence.

## Publication targets

- `.125` local staging: `\\192.0.2.125\kitling_QMT_work\kitling_bigqmt\BigQMT_Host_125`
- NAS release source: `\\192.0.2.236\truenas\kitling_QMT\kitling_bigqmt\releases\portable_host\candidate\0.2.0`

The NAS source is for controlled release distribution only. Each target copies
its designated folder locally before running it. The `checksums.sha256` file is
verified before publication.
