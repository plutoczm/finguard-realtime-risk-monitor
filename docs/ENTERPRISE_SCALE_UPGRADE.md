# 企业级规模升级设计

## 1. 升级目标

本次升级将 FinGuard 从个人实时计算 Demo 提升为企业级实时风控项目形态：

- 使用公开大规模 AML 合成交易数据，数据量约 1.45GB、约 6.9M 行。
- 保留 Kafka -> Flink -> File Sink 最小实时链路。
- 增加企业级 CSV 到支付交易事件 schema 的转换能力。
- 支持将企业级数据按 QPS 写入 Kafka 做压测。
- 增加 HDFS/Hive 等大数据组件的可选落地脚本。
- 增加本地智能风控大屏，展示交易规模、告警、风险等级、规则命中、城市/商户统计和智能研判。

## 2. 数据源选择

最终选择：

```text
Hugging Face: aaronzeller/small-aml-data
文件: amlworld_transactions_prepared.csv
大小: 1.45GB
行数: 约 6.9M
```

选择原因：

- 与支付交易和反洗钱风控场景高度匹配。
- 包含账户、银行、国家、金额、支付格式、洗钱标签、模型分数。
- 公开可下载，体积低于 40GB。
- 可映射到 FinGuard 的交易事件 schema。

备选数据源：

- Mendeley CreditTransAct：15M 笔信用卡交易，CC BY 4.0，适合信用卡欺诈离线分析。
- Kaggle PaySim：移动支付合成数据，体积较小，适合规则验证。

## 3. 数据目录

```text
enterprise_data/raw/amlworld_transactions_prepared.csv
enterprise_data/processed/finguard_enterprise_transactions.jsonl
enterprise_data/DATASET_MANIFEST.json
```

下载：

```powershell
python scripts/download_enterprise_dataset.py
```

转换：

```powershell
python producer/enterprise_dataset.py --limit 200000
```

全量转换：

```powershell
python producer/enterprise_dataset.py --limit 0
```

## 4. 企业级生产压测

将公开数据按 FinGuard schema 转为 Kafka 实时流：

```powershell
python producer/enterprise_kafka_producer.py --bootstrap-server localhost:9092 --topic payment_transaction_events --qps 500 --limit 100000
```

建议压测阶梯：

| 阶段 | QPS | 时长 | 观察 |
|---|---:|---:|---|
| L1 | 100 | 5 分钟 | Flink 作业是否稳定 |
| L2 | 500 | 10 分钟 | Kafka lag、Checkpoint 时长 |
| L3 | 1000 | 10 分钟 | 反压、Sink 小文件 |
| L4 | 3000+ | 15 分钟 | 并行度、热点 key、资源瓶颈 |

## 5. 对接本机大数据环境

你已经在 `E:\RetailPulseEnterprise` 中准备了：

- `HADOOP_HOME`
- `SPARK_HOME`
- `KAFKA_HOME`
- `HIVE_HOME`
- `HBASE_HOME`
- `FLINK_HOME`
- `SQOOP_HOME`
- `MAVEN_HOME`

项目脚本会优先使用这些持久化环境变量。可选落地路径：

```text
HDFS: /finguard/enterprise/raw/amlworld_transactions_prepared.csv
HDFS: /finguard/enterprise/processed/finguard_enterprise_transactions.jsonl
Hive: finguard_ods.ods_aml_transactions
Hive: finguard_dwd.dwd_payment_transaction_events
HBase: finguard:risk_alerts
```

## 6. 智能大屏

启动：

```powershell
python dashboard/server.py --port 8090
```

访问：

```text
http://localhost:8090
```

大屏展示：

- 实时交易笔数。
- 告警数量和高风险比例。
- 风险等级分布。
- 规则命中 TopN。
- 最近告警列表。
- 企业级数据规模。
- 智能研判建议。

## 7. 企业级边界

本次升级仍保持本地可运行，不把系统伪装成完整生产集群。真实生产还需要：

- Kafka 多 Broker 与副本。
- Flink RocksDB StateBackend 和远程 Checkpoint Storage。
- HDFS/S3/OSS 持久化。
- Schema Registry。
- 规则平台与审批流程。
- 数据血缘、质量校验、权限审计。
- Prometheus/Grafana 与统一告警平台。
