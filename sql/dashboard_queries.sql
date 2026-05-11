-- Alert volume by minute.
SELECT
    date_trunc('minute', alert_time) AS minute_bucket,
    count(*) AS alert_count
FROM risk_alerts
GROUP BY minute_bucket
ORDER BY minute_bucket DESC
LIMIT 60;

-- Alert distribution by risk level.
SELECT
    risk_level,
    count(*) AS alert_count
FROM risk_alerts
WHERE alert_time >= now() - interval '1 hour'
GROUP BY risk_level
ORDER BY alert_count DESC;

-- Top users by risk alerts.
SELECT
    user_id,
    count(*) AS alert_count,
    max(alert_time) AS last_alert_time
FROM risk_alerts
WHERE user_id IS NOT NULL
GROUP BY user_id
ORDER BY alert_count DESC
LIMIT 20;

-- Merchant receiving amount metric.
SELECT
    dimensions ->> 'merchant_id' AS merchant_id,
    max(value) AS latest_5m_amount,
    max(window_end) AS last_window_end
FROM realtime_metrics
WHERE metric_name = 'merchant_realtime_amount_5m'
GROUP BY dimensions ->> 'merchant_id'
ORDER BY latest_5m_amount DESC
LIMIT 20;

-- Channel success rate.
SELECT
    dimensions ->> 'channel' AS channel,
    avg(value) AS avg_success_rate
FROM realtime_metrics
WHERE metric_name = 'channel_success_rate_5m'
  AND window_end >= now() - interval '30 minutes'
GROUP BY dimensions ->> 'channel'
ORDER BY avg_success_rate ASC;

-- Late event count.
SELECT
    date_trunc('minute', created_at) AS minute_bucket,
    count(*) AS late_event_count
FROM late_events
GROUP BY minute_bucket
ORDER BY minute_bucket DESC
LIMIT 60;

-- Dead letter trend.
SELECT
    date_trunc('minute', created_at) AS minute_bucket,
    count(*) AS dead_letter_count
FROM dead_letter_events
GROUP BY minute_bucket
ORDER BY minute_bucket DESC
LIMIT 60;
