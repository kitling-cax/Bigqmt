-- BigQMT Coordinator PostgreSQL baseline.
-- This migration is a design artifact until a separately verified migration
-- runner applies it to an isolated shadow database. It does not alter SQLite
-- and must not be run against the current 18443 service database.

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version       TEXT PRIMARY KEY,
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    checksum      TEXT NOT NULL
);

CREATE SCHEMA IF NOT EXISTS catalog;
CREATE SCHEMA IF NOT EXISTS control;
CREATE SCHEMA IF NOT EXISTS runtime;
CREATE SCHEMA IF NOT EXISTS ledger;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS catalog.strategies (
    strategy_id          TEXT PRIMARY KEY,
    strategy_family_id   TEXT NOT NULL,
    exclusive_group      TEXT NOT NULL,
    display_name         TEXT NOT NULL,
    status                TEXT NOT NULL CHECK (status IN ('DRAFT', 'PUBLISHED', 'RETIRED')),
    created_at            TIMESTAMPTZ NOT NULL,
    updated_at            TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog.strategy_versions (
    strategy_id           TEXT NOT NULL REFERENCES catalog.strategies(strategy_id),
    version               TEXT NOT NULL,
    build_id              TEXT NOT NULL,
    manifest_sha256       CHAR(64) NOT NULL,
    bridge_rpc_version    TEXT NOT NULL,
    runtime_json          JSONB NOT NULL,
    published_at          TIMESTAMPTZ,
    publisher_commit      TEXT,
    status                TEXT NOT NULL CHECK (status IN ('CANDIDATE', 'PUBLISHED', 'REVOKED')),
    PRIMARY KEY (strategy_id, version, build_id)
);

CREATE TABLE IF NOT EXISTS catalog.release_artifacts (
    strategy_id           TEXT NOT NULL,
    version               TEXT NOT NULL,
    build_id              TEXT NOT NULL,
    relative_path         TEXT NOT NULL,
    sha256                CHAR(64) NOT NULL,
    size_bytes            BIGINT NOT NULL CHECK (size_bytes >= 0),
    nas_uri                TEXT NOT NULL,
    PRIMARY KEY (strategy_id, version, build_id, relative_path),
    FOREIGN KEY (strategy_id, version, build_id)
        REFERENCES catalog.strategy_versions(strategy_id, version, build_id)
);

CREATE TABLE IF NOT EXISTS catalog.backtest_runs (
    backtest_id           TEXT PRIMARY KEY,
    strategy_id           TEXT NOT NULL,
    version               TEXT,
    period_start          DATE NOT NULL,
    period_end            DATE NOT NULL,
    summary_json          JSONB NOT NULL,
    report_uri             TEXT,
    created_at            TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS control.hosts (
    host_id               TEXT PRIMARY KEY,
    hostname              TEXT,
    lan_address            INET,
    state                  TEXT NOT NULL,
    last_seen              TIMESTAMPTZ,
    fact_key_fingerprint   TEXT,
    created_at             TIMESTAMPTZ NOT NULL,
    updated_at             TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS control.host_profiles (
    host_id               TEXT NOT NULL REFERENCES control.hosts(host_id),
    profile_id            TEXT NOT NULL,
    account_id            TEXT NOT NULL,
    account_mode          TEXT NOT NULL CHECK (account_mode IN ('SIMULATION', 'PRODUCTION', 'PRODUCTION_READ_ONLY')),
    local_authority       TEXT NOT NULL CHECK (local_authority IN ('UNKNOWN', 'READ_ONLY', 'EXECUTION_CAPABLE')),
    key_fingerprint       TEXT,
    key_expires_at        TIMESTAMPTZ,
    observed_at           TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (host_id, profile_id)
);

CREATE TABLE IF NOT EXISTS control.strategy_assignments (
    assignment_id         TEXT PRIMARY KEY,
    strategy_account_id   TEXT NOT NULL,
    strategy_id           TEXT NOT NULL,
    strategy_version      TEXT NOT NULL,
    build_id              TEXT,
    exclusive_group       TEXT NOT NULL,
    target_host_id        TEXT NOT NULL REFERENCES control.hosts(host_id),
    assignment_epoch      BIGINT NOT NULL CHECK (assignment_epoch > 0),
    desired_state         TEXT NOT NULL CHECK (desired_state IN ('DEPLOY', 'RUN', 'PAUSE', 'STOP', 'REMOVE')),
    execution_mode        TEXT NOT NULL CHECK (execution_mode IN ('EXECUTE', 'READ_ONLY', 'SHADOW')),
    checkpoint_id         TEXT,
    requested_by          TEXT NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL,
    updated_at            TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_strategy_account_assignment
    ON control.strategy_assignments(strategy_account_id)
    WHERE desired_state IN ('DEPLOY', 'RUN', 'PAUSE');

CREATE UNIQUE INDEX IF NOT EXISTS one_active_exclusive_group_assignment
    ON control.strategy_assignments(exclusive_group)
    WHERE desired_state IN ('DEPLOY', 'RUN', 'PAUSE');

CREATE TABLE IF NOT EXISTS control.deployments (
    deployment_id        TEXT PRIMARY KEY,
    assignment_id        TEXT NOT NULL REFERENCES control.strategy_assignments(assignment_id),
    idempotency_key      TEXT NOT NULL UNIQUE,
    package_sha256       CHAR(64) NOT NULL,
    state                TEXT NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL,
    updated_at           TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS control.commands (
    command_id            TEXT PRIMARY KEY,
    host_id               TEXT NOT NULL REFERENCES control.hosts(host_id),
    command_type          TEXT NOT NULL,
    idempotency_key       TEXT NOT NULL UNIQUE,
    payload_json          JSONB NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL,
    expires_at            TIMESTAMPTZ,
    status                TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS control.command_results (
    command_id            TEXT PRIMARY KEY REFERENCES control.commands(command_id),
    host_id               TEXT NOT NULL REFERENCES control.hosts(host_id),
    status                TEXT NOT NULL,
    result_json           JSONB NOT NULL,
    received_at           TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime.strategy_accounts (
    strategy_account_id   TEXT PRIMARY KEY,
    broker_account_id     TEXT NOT NULL,
    initial_capital       NUMERIC(20, 4) NOT NULL CHECK (initial_capital >= 0),
    currency              TEXT NOT NULL DEFAULT 'CNY',
    status                TEXT NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL,
    updated_at            TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime.strategy_instances (
    instance_id           TEXT PRIMARY KEY,
    strategy_account_id   TEXT NOT NULL REFERENCES runtime.strategy_accounts(strategy_account_id),
    strategy_id           TEXT NOT NULL,
    strategy_version      TEXT NOT NULL,
    build_id              TEXT,
    host_id               TEXT NOT NULL REFERENCES control.hosts(host_id),
    assignment_epoch      BIGINT NOT NULL,
    state                 TEXT NOT NULL,
    execution_mode        TEXT NOT NULL,
    started_at            TIMESTAMPTZ,
    stopped_at            TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime.instance_status_history (
    status_event_id       TEXT PRIMARY KEY,
    instance_id           TEXT NOT NULL REFERENCES runtime.strategy_instances(instance_id),
    state                 TEXT NOT NULL,
    reason                TEXT,
    occurred_at           TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime.checkpoints (
    checkpoint_id         TEXT PRIMARY KEY,
    strategy_account_id   TEXT NOT NULL,
    strategy_id           TEXT NOT NULL,
    source_host_id        TEXT NOT NULL REFERENCES control.hosts(host_id),
    payload_sha256        CHAR(64) NOT NULL,
    nas_uri               TEXT NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger.orders (
    order_event_id        TEXT PRIMARY KEY,
    broker_account_id     TEXT NOT NULL,
    strategy_account_id   TEXT,
    strategy_instance_id  TEXT,
    broker_order_id       TEXT,
    symbol                TEXT NOT NULL,
    side                  TEXT NOT NULL,
    quantity              NUMERIC(20, 4) NOT NULL,
    price                 NUMERIC(20, 8),
    status                TEXT NOT NULL,
    event_time            TIMESTAMPTZ NOT NULL,
    received_at           TIMESTAMPTZ NOT NULL,
    payload_json          JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger.trades (
    trade_event_id        TEXT PRIMARY KEY,
    broker_account_id     TEXT NOT NULL,
    strategy_account_id   TEXT,
    strategy_instance_id  TEXT,
    broker_trade_id       TEXT NOT NULL,
    symbol                TEXT NOT NULL,
    side                  TEXT NOT NULL,
    quantity              NUMERIC(20, 4) NOT NULL,
    price                 NUMERIC(20, 8) NOT NULL,
    fees                  NUMERIC(20, 8) NOT NULL DEFAULT 0,
    trade_time            TIMESTAMPTZ NOT NULL,
    received_at           TIMESTAMPTZ NOT NULL,
    payload_json          JSONB NOT NULL,
    UNIQUE (broker_account_id, broker_trade_id)
);

CREATE TABLE IF NOT EXISTS ledger.current_positions (
    broker_account_id     TEXT NOT NULL,
    strategy_account_id   TEXT,
    symbol                TEXT NOT NULL,
    quantity              NUMERIC(20, 4) NOT NULL,
    available_quantity    NUMERIC(20, 4) NOT NULL,
    average_cost          NUMERIC(20, 8),
    market_price          NUMERIC(20, 8),
    as_of                 TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (broker_account_id, strategy_account_id, symbol)
);

CREATE TABLE IF NOT EXISTS ledger.nav_snapshots (
    snapshot_id           TEXT PRIMARY KEY,
    strategy_account_id   TEXT NOT NULL REFERENCES runtime.strategy_accounts(strategy_account_id),
    as_of                 TIMESTAMPTZ NOT NULL,
    cash                  NUMERIC(20, 8) NOT NULL,
    market_value          NUMERIC(20, 8) NOT NULL,
    nav                   NUMERIC(20, 8) NOT NULL,
    realized_pnl          NUMERIC(20, 8) NOT NULL DEFAULT 0,
    unrealized_pnl        NUMERIC(20, 8) NOT NULL DEFAULT 0,
    drawdown              NUMERIC(20, 8),
    UNIQUE (strategy_account_id, as_of)
);

CREATE TABLE IF NOT EXISTS ledger.daily_performance (
    strategy_account_id   TEXT NOT NULL REFERENCES runtime.strategy_accounts(strategy_account_id),
    trading_date          DATE NOT NULL,
    start_nav             NUMERIC(20, 8) NOT NULL,
    end_nav               NUMERIC(20, 8) NOT NULL,
    daily_return          NUMERIC(20, 10),
    cumulative_return     NUMERIC(20, 10),
    max_drawdown          NUMERIC(20, 10),
    PRIMARY KEY (strategy_account_id, trading_date)
);

CREATE TABLE IF NOT EXISTS audit.fact_events (
    event_id              TEXT PRIMARY KEY,
    event_type            TEXT NOT NULL,
    host_id               TEXT NOT NULL REFERENCES control.hosts(host_id),
    strategy_account_id   TEXT,
    strategy_instance_id  TEXT,
    occurred_at           TIMESTAMPTZ NOT NULL,
    received_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    sequence_no           BIGINT,
    payload_json          JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS audit.ingest_requests (
    request_id            TEXT PRIMARY KEY,
    host_id               TEXT NOT NULL REFERENCES control.hosts(host_id),
    idempotency_key       TEXT NOT NULL UNIQUE,
    event_count            INTEGER NOT NULL CHECK (event_count >= 0),
    status                TEXT NOT NULL,
    received_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit.operator_actions (
    action_id             TEXT PRIMARY KEY,
    operator_id           TEXT NOT NULL,
    action_type            TEXT NOT NULL,
    target_type            TEXT NOT NULL,
    target_id              TEXT NOT NULL,
    request_json           JSONB NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.alerts (
    alert_id              TEXT PRIMARY KEY,
    severity              TEXT NOT NULL,
    alert_type            TEXT NOT NULL,
    target_id              TEXT,
    status                TEXT NOT NULL,
    details_json          JSONB NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL,
    resolved_at            TIMESTAMPTZ
);

COMMIT;
