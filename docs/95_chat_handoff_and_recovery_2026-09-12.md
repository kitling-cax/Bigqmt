# Chat handoff and recovery record — 2026-09-12

## User request in progress

The user asked to continue completing the BigQMT project.  During the active
turn, Codex Desktop reported that it could not load its user `config.toml`
because model provider `opencodex` was not found.  The user asked for this
conversation to be recorded before the configuration is repaired.

## Completed BigQMT state

- Project: `C:\BigQMT\work\kitling_bigqmt`.
- Simulation account `90000001`: strategy sleeve
  `S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15`, initial capital 100,000 CNY.
- Formal account `90000002`: permanently read-only; no order/cancel route.
- Actual attributable simulation entry: `160723.SZ`, 41,400 shares, QMT order
  system id `365`; fills are recorded in the simulation SQLite WAL.
- Real-fill ownership is now durable across Redis restarts: `user_order_id`
  plus QMT `order_sys_id` are validated against local strategy order
  attribution before a generic `BIGQMT_BRIDGE` trade may affect the sleeve.
- Ordinary rotations obey the actual QMT fill date and five QMT-calendar
  sessions.  `RISK_*` exits retain the frozen v1.1.15 semantics.
- Simulation Tray runs a bounded weekday scheduler after 09:35 only.  It
  requires QMT calendar, fresh broker facts, reconciliation, attribution, and
  a 120-second order-control window.  It immediately re-locks afterward.
- Simulation and production-readonly trays are running.  Redis ports 6379 and
  6380, dashboards 17890 and 17891, Bridge snapshots, and locks all passed
  health checks at the end of the prior turn.
- Both profiles currently report `READ_ONLY_LOCKED`; no order was submitted
  during the recovery work.

## Key files and evidence

- `progress/current_status.json`
- `docs/94_v1_1_15_durable_order_attribution_and_tray_schedule_2026-09-12.md`
- `runtime_data/evidence/simulation/daily_operations/v1_1_15_daily_20260912_170743.json`
- `runtime_data/evidence/simulation/strategy_execution_cycles/v1_1_15_cycle_20260912_170756.json`
- `runtime_data/state/simulation/qmt_runtime.sqlite3`

## Verification already completed

- Python test suite: `87 passed`.
- Simulation health: `HEALTHY`, orders disabled.
- Production-readonly health: `HEALTHY`, orders disabled.
- The latest cycle was blocked outside the bounded trading window with
  `broker_call_made=false`.

## Immediate recovery task

Repair the user-level Codex configuration at
`C:\Users\developer\.codex\config.toml`.  The error indicates that its selected
`model_provider` is `opencodex` but no matching `[model_providers.opencodex]`
definition is currently available.  Existing OpenCodex injection recovery
data remains in `C:\Users\developer\.codex\opencodex-journal.json`, alongside
the existing `config.toml.bak-*` snapshots.

## Recovery completed

At 2026-09-12 18:xx local time the user-level configuration was repaired by
explicitly setting `model_provider = "openai"`.  The existing OpenCodex
Design-B proxy settings were retained:

- `openai_base_url = "http://127.0.0.1:10100/v1"`
- `experimental_realtime_ws_base_url = "http://127.0.0.1:10100/v1"`
- `model_catalog_json = "C:\\Users\\kitling\\.codex\\opencodex-catalog.json"`

Python `tomllib` successfully parsed the resulting configuration and confirmed
the selected provider is `openai`.  Codex should now be restarted or this
conversation reopened so the desktop process reloads the user configuration.
