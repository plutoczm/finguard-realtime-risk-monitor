# Enterprise Dataset

本目录用于放置企业级公开交易数据和转换后的 FinGuard 事件数据。

## 当前数据源

数据集：`aaronzeller/small-aml-data`

来源：

- Hugging Face Dataset: `https://huggingface.co/datasets/aaronzeller/small-aml-data`
- 原始说明引用 IBM Transactions for Anti Money Laundering synthetic dataset
- IBM Research 论文：Realistic Synthetic Financial Transactions for Anti-Money Laundering Models

规模：

- CSV 文件：`amlworld_transactions_prepared.csv`
- 文件大小：约 1.45GB
- 行数级别：约 6.9M 笔交易
- 低于本项目要求的 40GB 上限

## 文件路径

```text
enterprise_data/
  raw/
    amlworld_transactions_prepared.csv
  processed/
    finguard_enterprise_transactions.jsonl
    finguard_enterprise_transactions.jsonl.metadata.json
```

## 下载

```powershell
python scripts/download_enterprise_dataset.py
```

该脚本支持断点续传。网络中断后重复执行即可。

## 转换为 FinGuard 事件

默认转换 20 万行：

```powershell
python producer/enterprise_dataset.py --limit 200000
```

转换全量：

```powershell
python producer/enterprise_dataset.py --limit 0
```

## 直接写入 Kafka

```powershell
python producer/enterprise_kafka_producer.py --bootstrap-server localhost:9092 --topic payment_transaction_events --qps 500 --limit 100000
```

## 字段映射

| AML CSV 字段 | FinGuard 字段 |
|---|---|
| `record_key` | `event_id` / `transaction_id` 的稳定 hash 来源 |
| `from_account` | `user_id` / `account_id` |
| `to_bank` + `to_account` | `merchant_id` |
| `amount_paid` | `amount` |
| `payment_currency` | `currency` |
| `payment_format` | `payment_method` / `transaction_type` |
| `timestamp` | `event_time` |
| `is_laundering` / `model_score` | `risk_label` / `is_black_device` / `is_black_card` |
