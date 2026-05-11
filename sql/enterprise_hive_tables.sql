CREATE DATABASE IF NOT EXISTS finguard_ods;
CREATE DATABASE IF NOT EXISTS finguard_dwd;

CREATE EXTERNAL TABLE IF NOT EXISTS finguard_ods.ods_aml_transactions (
    record_key STRING,
    event_ts STRING,
    from_bank STRING,
    from_account STRING,
    from_country STRING,
    to_bank STRING,
    to_account STRING,
    to_country STRING,
    amount_received DOUBLE,
    receiving_currency STRING,
    amount_paid DOUBLE,
    payment_currency STRING,
    payment_format STRING,
    is_laundering BOOLEAN,
    predicted_alert BOOLEAN,
    model_score DOUBLE,
    is_dashboard_sample BOOLEAN
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
    "separatorChar" = ",",
    "quoteChar" = "\"",
    "escapeChar" = "\\"
)
STORED AS TEXTFILE
LOCATION '/finguard/enterprise/raw'
TBLPROPERTIES ("skip.header.line.count"="1");

CREATE EXTERNAL TABLE IF NOT EXISTS finguard_dwd.dwd_payment_transaction_events (
    event_id STRING,
    transaction_id STRING,
    user_id STRING,
    account_id STRING,
    card_id STRING,
    merchant_id STRING,
    device_id STRING,
    ip STRING,
    province STRING,
    city STRING,
    amount DOUBLE,
    currency STRING,
    payment_method STRING,
    transaction_type STRING,
    transaction_status STRING,
    event_time STRING,
    process_time STRING,
    channel STRING,
    app_version STRING,
    is_black_device BOOLEAN,
    is_black_card BOOLEAN,
    risk_label STRING
)
ROW FORMAT SERDE 'org.apache.hive.hcatalog.data.JsonSerDe'
STORED AS TEXTFILE
LOCATION '/finguard/enterprise/processed';
