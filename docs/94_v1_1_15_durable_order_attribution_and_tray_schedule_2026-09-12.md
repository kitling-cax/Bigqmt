# v1.1.15 durable order attribution and Tray schedule — 2026-09-12

## Scope

This delivery strengthens the simulation-only execution adapter for
`S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15`.  It does not change the frozen
v1.1.15 signal, ranking, SMA, risk, position sizing, or its formal-account
boundary.  Account `90000002` remains read-only.

## Redis restart recovery

QMT returned the 2026-09-11 actual fills after a Redis restart with
`strategy_name=BIGQMT_BRIDGE`.  That generic bridge name is not ownership
proof.  The simulation WAL now stores an immutable attribution containing:

- account `90000001`;
- QMT `user_order_id=v1_1_15-entry-20260910-14dac123f8`;
- QMT `order_sys_id=365`;
- expected `BUY 160723.SZ 41,400`; and
- the original submission evidence
  `runtime_data/evidence/simulation/strategy_execution/v1_1_15_entry_20260911_102034.json`.

Only a generic bridge row whose user/system order identity and code/side/
quantity agree with this local proof can update the sleeve.  An unrelated
shared-account fill is ignored.  A row that claims a known identity while
disagreeing with it blocks reconciliation.  New Tray-issued QMT orders must
persist the same proof before their execution attempt is finalized.

The read-only verification at 2026-09-12 17:07 found the two known fills as
idempotent duplicates, with no new sleeve fill, no broker order, and a passed
external-baseline reconciliation.

## Scheduled simulation cycle

`tray/BigQMTTray.ps1` is now the simulation scheduler.  On a weekday it makes
at most one attempt after 09:35 and before 14:50 local time.  The Python
cycle independently verifies QMT's exchange calendar, fresh account/quote
facts, no open orders, sleeve/external-baseline reconciliation, durable fill
attribution, and the actual-fill holding-period guard.  It arms the order
route for only 120 seconds and re-locks it in `finally`.

Only transient Redis/RPC connectivity errors retry after ten minutes.  A
calendar, holding-period, risk, open-order, or reconciliation block completes
the day's attempt without another order attempt.  Weekends and the production
read-only profile never enter this scheduler.

## Validation

- Unit suite: `87 passed`.
- `scripts/record_v1_1_15_simulation_daily.py`: `PASSED`, sleeve NAV
  `98,348.88664`, orders locked.
- `scripts/run_v1_1_15_simulation_cycle.py`: blocked outside the bounded
  execution window; `broker_call_made=false`.
- `scripts/check_tray_health.py --profile simulation --port 17890`:
  `HEALTHY`; Redis, Bridge snapshot, dashboard, and lock all passed.

Both tray profiles were restarted after this release and their health checks
passed.  The Tray now also starts a *missing* profile-local Redis listener
from its pinned project configuration (`6379` for simulation, `6380` for
production-readonly).  It does not terminate a listener, restart QMT, or
change an order lock.  The production Redis listener had been absent, was
started with `redis-production.conf`, and then passed its read-only health
check.  This document itself grants no new formal-account permissions.
