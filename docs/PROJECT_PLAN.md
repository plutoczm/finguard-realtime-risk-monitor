# FinGuard 项目实施计划

## 1. 项目范围

FinGuard 是一个面向互联网支付平台的实时风控与异常监控项目。项目从零设计业务主题、事件模型、Kafka Topic、Flink 实时作业、风险规则、文件 Sink、本地 Docker 环境、测试和文档。

本项目默认目标是先跑通最小端到端链路：

```text
Python Producer -> Kafka -> Flink RiskMonitorJob -> File Sink
```

在此基础上，文档中给出 PostgreSQL、ClickHouse、Grafana 等可选扩展方案。

## 2. 里程碑

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| M1 | 项目计划与 Agent 分工 | `docs/PROJECT_PLAN.md`、`docs/AGENTS.md` 完成 |
| M2 | 目录结构 | 按约定创建 producer、flink-job、sql、docs、tests、data、reports 等目录 |
| M3 | Kafka 事件层 | 支持生成正常、异常、乱序、迟到、重复、高峰流量事件 |
| M4 | Flink 计算层 | Java DataStream 作业实现解析、Watermark、窗口、状态、去重、迟到旁路、告警与指标输出 |
| M5 | Sink 层 | 默认文件 Sink 可运行，SQL 给出数据库扩展建表与查询 |
| M6 | DevOps | Docker Compose、Makefile、PowerShell、Topic 脚本适配 Windows 11 |
| M7 | 测试 | Python 单测覆盖 schema、规则阈值、去重、迟到判断；Java 测试覆盖核心工具 |
| M8 | 文档 | README 和 docs 文档完整，面试问答不少于 35 个 |
| M9 | 验证 | 能执行 `make up`、`make create-topics`、`make produce`、`make submit-job`、`make test` |

## 3. 技术选型

| 模块 | 选择 | 原因 |
|---|---|---|
| 消息队列 | Kafka | 高吞吐、可重放、天然适合作为实时事件日志 |
| 实时计算 | Flink Java DataStream API | 原生事件时间、Watermark、状态、窗口、Checkpoint 语义清晰 |
| 事件生成 | Python | 本地快速模拟交易事件，便于压测和调参 |
| 默认 Sink | File Sink | 不依赖外部数据库，保证最小链路在本地可跑 |
| 本地环境 | Docker Compose | Windows 11 + Docker Desktop + WSL2 下可复现 |
| 测试 | pytest + JUnit | 覆盖 Python producer 与 Java 工具逻辑 |

## 4. 运行环境边界

建议环境：

- Windows 11
- VSCode
- Docker Desktop，开启 WSL2 backend
- CPU 4 核以上
- 内存 8GB 以上
- Java 17
- Maven 3.8+
- Python 3.10+

默认端口：

| 服务 | 端口 |
|---|---|
| Kafka | `localhost:9092` |
| Flink UI | `http://localhost:8081` |
| PostgreSQL 可选 | `localhost:5432` |
| ClickHouse 可选 | `http://localhost:8123` |
| Grafana 可选 | `http://localhost:3000` |

## 5. 风控规则范围

本期实现 8 条规则：

| Rule ID | 规则 | 风险等级 |
|---|---|---|
| R001 | 同一用户 1 分钟交易次数超过 10 次 | MEDIUM |
| R002 | 同一用户 5 分钟累计交易金额超过 20,000 元 | HIGH |
| R003 | 同一设备 10 分钟关联超过 5 个用户 | HIGH |
| R004 | 同一银行卡 10 分钟关联超过 3 个用户 | HIGH |
| R005 | 同一用户连续支付失败超过 5 次 | MEDIUM |
| R006 | 黑名单设备交易 | HIGH |
| R007 | 当前交易金额超过用户历史均值 5 倍 | MEDIUM |
| R008 | 商户 5 分钟收款金额超过历史均值 3 倍 | HIGH |

## 6. 执行顺序

1. 生成 `docs/PROJECT_PLAN.md`。
2. 生成 `docs/AGENTS.md`。
3. 创建目录结构。
4. 实现事件生成器。
5. 实现 Kafka Topic 脚本。
6. 实现 Flink 作业。
7. 实现文件 Sink 与 SQL 扩展。
8. 实现测试。
9. 实现 Docker Compose、Makefile、PowerShell。
10. 实现 README 和文档。
11. 给出本地运行步骤。

## 7. 验收清单

- [ ] `producer/generate_transactions.py` 能生成 JSON Lines 样例事件。
- [ ] `producer/kafka_producer.py` 能按 QPS 往 Kafka 写交易事件。
- [ ] `scripts/create_topics.sh` 能创建 6 个指定 Topic。
- [ ] `flink-job` 能打包出可提交到 Flink 的 JAR。
- [ ] Flink 作业包含事件时间、Watermark、滚动窗口、滑动窗口、Keyed State、State TTL、Checkpoint、迟到旁路、event_id 去重。
- [ ] 默认文件 Sink 输出实时指标、风险告警、迟到事件、死信事件。
- [ ] `pytest` 测试通过。
- [ ] README 能支撑简历和面试讲解。
- [ ] 文档诚实说明端到端一致性边界。
