-- FinGuard optional database sink tables.
-- The default runnable path uses Flink File Sink. These tables are for PostgreSQL/ClickHouse style dashboard extensions.

CREATE TABLE IF NOT EXISTS risk_alerts (
    alert_id            VARCHAR(64) PRIMARY KEY,
    rule_id             VARCHAR(16) NOT NULL,
    rule_name           VARCHAR(128) NOT NULL,
    risk_level          VARCHAR(16) NOT NULL,
    reason              TEXT NOT NULL,
    event_id            VARCHAR(128),
    transaction_id      VARCHAR(128),
    user_id             VARCHAR(64),
    account_id          VARCHAR(64),
    card_id             VARCHAR(64),
    merchant_id         VARCHAR(64),
    device_id           VARCHAR(64),
    amount              NUMERIC(18, 2),
    event_time          TIMESTAMPTZ,
    alert_time          TIMESTAMPTZ,
    window_start        TIMESTAMPTZ,
    window_end          TIMESTAMPTZ,
    evidence            JSONB,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS realtime_metrics (
    metric_id           VARCHAR(64) PRIMARY KEY,
    metric_name         VARCHAR(128) NOT NULL,
    dimensions          JSONB,
    value               NUMERIC(20, 6),
    count_value         BIGINT,
    window_start        TIMESTAMPTZ,
    window_end          TIMESTAMPTZ,
    emit_time           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS late_events (
    event_id            VARCHAR(128) PRIMARY KEY,
    transaction_id      VARCHAR(128),
    user_id             VARCHAR(64),
    merchant_id         VARCHAR(64),
    event_time          TIMESTAMPTZ,
    process_time        TIMESTAMPTZ,
    raw_event           JSONB,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dead_letter_events (
    dead_letter_id      BIGSERIAL PRIMARY KEY,
    topic               VARCHAR(128),
    raw_event           TEXT NOT NULL,
    error_message       TEXT,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_risk_alerts_rule_window
ON risk_alerts (rule_id, COALESCE(user_id, ''), COALESCE(device_id, ''), COALESCE(card_id, ''), COALESCE(merchant_id, ''), window_start, window_end);

CREATE INDEX IF NOT EXISTS idx_risk_alerts_level_time
ON risk_alerts (risk_level, alert_time DESC);

CREATE INDEX IF NOT EXISTS idx_realtime_metrics_name_window
ON realtime_metrics (metric_name, window_start, window_end);

-- Idempotent PostgreSQL write example:
-- INSERT INTO risk_alerts (...) VALUES (...)
-- ON CONFLICT (alert_id) DO UPDATE
-- SET evidence = EXCLUDED.evidence, alert_time = EXCLUDED.alert_time;

-- ClickHouse extension idea:
-- Use ReplacingMergeTree(alert_version) with alert_id as the deduplication key.
-- This is eventually deduplicated, not immediate exactly-once.
