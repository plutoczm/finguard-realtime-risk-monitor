# FinGuard 多 Agent 分工

本项目用多 Agent 思路拆分设计与实现责任。每个 Agent 的产出都落在明确文件中，最终由主流程统一集成。

## Agent A：Project Manager Agent

职责：

- 控制项目范围和里程碑。
- 保证项目能在 Windows 11 + VSCode + Docker Desktop + WSL2 环境运行。
- 保证项目能写进简历并能在面试中讲清楚。

产出文件：

- `docs/PROJECT_PLAN.md`
- `README.md` 中的项目目标、运行步骤、简历写法、3 分钟讲解稿

验收标准：

- 项目边界清晰，不依赖复杂外部服务也能跑通最小链路。
- README 能解释项目价值、技术栈、运行方式和面试亮点。

## Agent B：Streaming Architecture Agent

职责：

- 设计整体实时架构。
- 设计 Kafka -> Flink -> Sink 链路。
- 设计 Topic、事件 schema、状态、窗口、Watermark、告警规则。

产出文件：

- `docs/ARCHITECTURE.md`
- `docs/KAFKA_DESIGN.md`
- `producer/event_schema.json`

验收标准：

- 架构图完整。
- Topic 与事件模型贴近支付风控。
- Watermark、窗口、状态和迟到数据处理策略解释清楚。

## Agent C：Kafka Event Agent

职责：

- 设计 Kafka Topics。
- 编写事件生成器。
- 支持正常交易、异常交易、乱序事件、迟到事件、重复事件、高峰流量。
- 支持命令行参数控制 QPS、持续时间、异常比例。

产出文件：

- `producer/generate_transactions.py`
- `producer/kafka_producer.py`
- `producer/event_schema.json`
- `data/sample_events/transactions.json`

验收标准：

- 能生成符合 schema 的交易事件。
- 能按 `--qps`、`--duration`、`--mode`、`--abnormal-rate` 控制事件流。
- 支持示例命令中要求的模式。

## Agent D：Flink Stream Processing Agent

职责：

- 编写 Flink 实时作业。
- 使用 Java Flink DataStream API。
- 实现事件解析、Watermark、窗口聚合、状态去重、风险规则判断、迟到数据 side output、指标 sink、告警 sink。

产出文件：

- `flink-job/pom.xml`
- `flink-job/src/main/java/com/finguard/RiskMonitorJob.java`
- `flink-job/src/main/java/com/finguard/model/*`
- `flink-job/src/main/java/com/finguard/function/*`
- `flink-job/src/main/java/com/finguard/sink/*`
- `flink-job/src/main/java/com/finguard/utils/*`

验收标准：

- 作业可打包。
- 代码中体现 Event Time、Watermark、Tumbling Window、Sliding Window、Keyed State、State TTL、Checkpoint、Side Output、event_id 去重。
- 至少输出文件 Sink 到 `data/output/realtime_metrics`、`data/alerts/risk_alerts`、`data/late_events`。

## Agent E：Risk Rule Agent

职责：

- 设计并实现 8 条风控规则。
- 每条规则具备 `rule_id`、`rule_name`、`risk_level`、`reason`。

产出文件：

- `flink-job/src/main/java/com/finguard/function/*RuleFunction.java`
- `flink-job/src/main/java/com/finguard/utils/RuleConstants.java`
- `docs/RISK_RULES.md`

验收标准：

- 8 条规则全部在代码或文档中可追踪。
- 告警输出包含证据字段，能解释为何命中。

## Agent F：State & Reliability Agent

职责：

- 设计 Flink state。
- 实现 event_id 去重。
- 设置 state TTL。
- 配置 checkpoint。
- 说明失败恢复、exactly-once、at-least-once、幂等写入边界。

产出文件：

- `docs/STATE_AND_RELIABILITY.md`
- `flink-job/src/main/java/com/finguard/function/EventDeduplicateFunction.java`

验收标准：

- 文档不夸大端到端 exactly-once。
- 清楚说明文件 Sink 与下游读取的幂等边界。
- 代码中使用 TTL 保护高基数状态。

## Agent G：Sink & Dashboard Agent

职责：

- 设计指标和告警输出。
- 默认实现本地文件 sink。
- 编写 SQL 建表和 dashboard 查询。

产出文件：

- `sql/sink_tables.sql`
- `sql/dashboard_queries.sql`
- `reports/realtime_result_sample.md`
- `reports/risk_alert_sample.md`

验收标准：

- 文件 Sink 路径清楚。
- SQL 包含 alert、metric、late event、dead letter 表。
- Dashboard 查询能支撑告警数、风险等级分布、商户金额、城市金额等展示。

## Agent H：DevOps on Windows Agent

职责：

- 编写 Docker Compose、Makefile、PowerShell 脚本、依赖文件。
- 适配 Windows 11。
- 写清楚 Docker Desktop 内存建议、端口说明、启动与清理命令。

产出文件：

- `docker-compose.yml`
- `Makefile`
- `.env.example`
- `requirements.txt`
- `scripts/run_all.ps1`
- `scripts/create_topics.sh`
- `scripts/clean.sh`

验收标准：

- `make up`、`make down`、`make create-topics`、`make generate`、`make produce`、`make submit-job`、`make logs`、`make clean`、`make test` 有定义。
- PowerShell 一键脚本可在 Windows 中启动基础链路。

## Agent I：Testing Agent

职责：

- 编写测试。
- 测试事件 schema。
- 测试风控规则。
- 测试去重逻辑。
- 测试迟到事件判断。

产出文件：

- `tests/test_event_schema.py`
- `tests/test_risk_rules.py`
- `tests/test_dedup_logic.py`
- `flink-job/src/test/java/com/finguard/RiskAlertFactoryTest.java`

验收标准：

- `pytest` 能验证 Python 事件生成与规则逻辑。
- Maven 测试能验证 Java 告警 ID 稳定性。

## Agent J：Documentation & Interview Agent

职责：

- 编写 README 和完整设计文档。
- 编写不少于 35 个面试问答。
- 确保项目外观看起来是独立个人项目。

产出文件：

- `README.md`
- `docs/FLINK_DESIGN.md`
- `docs/WATERMARK_AND_LATE_DATA.md`
- `docs/INTERVIEW_QA.md`
- `docs/REFERENCES.md`

验收标准：

- README 不出现“二次开发某仓库”的表述。
- `docs/INTERVIEW_QA.md` 至少 35 问。
- 文档覆盖 Kafka、Flink、状态、窗口、一致性、反压、扩展和简历表达。
