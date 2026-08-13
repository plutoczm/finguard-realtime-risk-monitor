# FinGuard 面试问答（AI 应用开发岗）

## 1. 项目定位

### Q1：FinGuard 是什么？
FinGuard 是一个支付交易实时风险监控系统。Kafka + Flink 负责确定性的低延迟风险检测，AI Risk Copilot 负责把结构化告警转换为人工分析员可读的解释、证据摘要和调查步骤。

### Q2：为什么不是直接让 LLM 判断一笔交易是否欺诈？
支付授权是高风险、低延迟、强可解释场景。LLM 存在延迟抖动、供应商故障和生成不确定性，因此不应成为硬实时控制面的单点依赖。项目把 LLM 放在检测之后做 decision support，主链路仍由规则和流计算保证确定性。

### Q3：项目最核心的工程取舍是什么？
不是“用了多少组件”，而是把职责边界切清楚：Kafka 承载事件日志，Flink 处理状态和时间语义，File Sink 提供最小可运行输出，Dashboard 做可视化，AI Copilot 只做解释与调查辅助。

## 2. 实时链路

### Q4：为什么用 Kafka？
需要把事件生产与实时计算解耦，并支持按 key 分区、积压缓冲和重放。当前只创建 `payment_transaction_events` 一个业务 Topic，因为其他输出还没有真实 Kafka 消费方。

### Q5：为什么 Kafka 只有一个 Topic？
当前运行代码只消费交易事件，告警、指标、迟到和死信由 Flink File Sink 输出。如果提前创建一堆“未来可能用到”的 Topic，只会增加配置和解释成本；等真实下游出现再拆分。

### Q6：为什么使用 KRaft 而不是 ZooKeeper？
本地开发只需要一个 Kafka 节点，因此使用 KRaft combined mode 可以减少一个基础设施服务。生产环境不会照搬这个单节点拓扑，而应使用独立 controller/broker 和多副本配置。

### Q7：Event Time 和 Processing Time 有什么区别？
Event Time 是交易真实发生时间，Processing Time 是算子处理时间。风控窗口依赖交易发生顺序，因此使用 Event Time，避免 Kafka 延迟或消费抖动改变窗口归属。

### Q8：Watermark 太短或太长分别有什么问题？
太短会让正常乱序事件过早变成迟到数据；太长会增加窗口完成和告警输出延迟。项目默认容忍 60 秒乱序，并把严重迟到数据旁路输出。

### Q9：如何处理重复事件？
按 `event_id` keyBy，用带 TTL 的 Keyed State 记录是否已经处理。这样能覆盖 Producer 重试、重放和恢复过程中可能出现的重复。

### Q10：项目是否端到端 exactly-once？
不夸大全链路。Kafka Source offset、Flink state 和 checkpoint-aware File Sink 有明确的一致性恢复边界；下游仍应使用稳定 `alert_id` 做幂等。

## 3. AI Copilot

### Q11：LLM 的输入是什么？
输入是结构化 `RiskAlert`、最小化交易上下文和最多 20 条近期事件，而不是整份用户画像或原始日志。

### Q12：如何避免把敏感信息直接发给模型？
在模型调用前做 PII minimization：用户、设备、商户等标识符转换为不可逆短哈希引用；原始 IP 不发送；`evidence` 内部也递归处理 `_id` 和 IP 字段。

### Q13：如何降低幻觉？
系统 prompt 明确要求只能使用提供的告警上下文，不允许引入外部事实或因果结论；输出必须包含 `key_evidence` 和 `limitations`。这不是从根本上消灭幻觉，而是把生成约束成可审计的调查辅助。

### Q14：为什么用 Structured Outputs？
下游 UI/API 需要稳定字段，而不是解析自然语言。模型输出被限制为 JSON Schema，必须返回 `summary`、`recommended_action`、`confidence`、`key_evidence`、`investigation_steps` 和 `limitations`。

### Q15：模型超时或不可用怎么办？
`RiskExplainer` 捕获缺少 API Key、超时、供应商异常、JSON 解析和 Schema 校验错误，自动切到确定性 fallback。fallback 根据规则 ID 和风险等级给出固定格式的解释和调查步骤，因此 AI 故障不会让风控工作流不可用。

### Q16：为什么 fallback 不是简单返回 500？
这个接口服务的是人工处置流程。模型增强能力可以降级，但基础解释能力不能消失；因此 fallback 是业务级 graceful degradation，而不是单纯技术异常处理。

### Q17：如何做 prompt 版本管理？
每个响应都返回 `prompt_version`。这样评测结果、线上异常和人工反馈可以定位到具体 prompt 版本，避免修改 prompt 后无法解释结果变化。

### Q18：为什么不引入 LangChain/Agent/向量数据库？
当前任务只是基于结构化告警生成调查解释，不需要复杂工具编排，也没有检索知识库需求。直接使用模型 SDK + Pydantic + JSON Schema 更短、更透明、更容易测试。出现真实 RAG 或多工具调用需求后再引入框架。

## 4. AI 评测与可观测性

### Q19：AI 功能怎么测试？
分两层：单元测试验证脱敏、fallback 和无 Key 场景；golden set 验证推荐动作、关键证据覆盖和输出完整性。默认评测不调用外部模型，所以 CI 可重复执行。

### Q20：为什么 golden set 不能说明模型已经“准确”？
当前集合规模很小，只能验证输出契约和基础行为。真实上线需要人工标注的风险案例，并分别统计 grounded evidence rate、action agreement、schema-valid rate、fallback rate 和人工采纳率。

### Q21：线上最重要的 AI 指标是什么？
至少要看 p50/p95 latency、fallback rate、结构化输出成功率、token/cost、人工采纳率、证据一致性和不同规则/风险等级下的错误分布。

### Q22：`confidence` 能直接当概率吗？
不能。当前 confidence 是模型/策略输出的辅助字段，没有经过概率校准。生产中若要用于排序或阈值决策，需要单独做校准与验证。

## 5. 工程化

### Q23：为什么 AI 服务单独做 FastAPI？
把模型依赖、输入输出契约、降级策略和监控封装成独立边界，便于 Dashboard、工单系统或其他服务复用，也便于独立压测和替换模型供应商。

### Q24：CI 检查什么？
Python job 做依赖安装、compileall、pytest 和 golden-set eval；Java job 单独运行 Flink Maven 测试。AI 评测默认不需要密钥，避免 CI 依赖外部供应商。

### Q25：为什么没有把 PostgreSQL、Hive、Grafana、Schema Registry 全加上？
因为它们目前没有进入核心闭环。作品项目更重要的是每一个依赖都能回答“谁在用、为什么需要、失败怎么办”。只有出现持久查询、数据治理或监控需求时再增加相应组件。

## 6. 下一步真实演进

### Q26：如果要继续做成更强的 AI 应用，下一步是什么？
优先级不是继续加基础设施，而是：把 Copilot 接入告警详情 UI；扩大人工标注 eval 数据集；记录模型延迟/成本/接受率；加入请求级 trace；增加 prompt injection 与敏感字段测试；最后再根据真实需求考虑规则知识 RAG 或工具调用。

### Q27：如果要扩展实时检测能力呢？
可以把规则阈值从代码迁移为版本化配置，并通过广播状态热更新；再基于压测结果调整 Kafka 分区和 Flink 并行度，而不是先假设需要更多中间件。
