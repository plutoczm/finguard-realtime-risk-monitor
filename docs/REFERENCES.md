# 参考资料

本项目是围绕支付实时风控重新设计的个人原创项目。实现过程中参考了以下公开资料中的通用思想：

- Apache Flink 官方文档：DataStream API、Event Time、Watermark、State、Checkpoint、File Sink。
- Apache Kafka 官方文档：Topic、Partition、Producer、Consumer、Offset。
- Docker Compose 官方文档：本地多服务编排方式。
- 公开 Flink playground 与官方示例中的通用运行方式，例如 Kafka + Flink + Docker Compose 的本地演示思路。
- Hugging Face Dataset `aaronzeller/small-aml-data`：用于企业级 AML 合成金融交易数据演示。
- IBM Research AML synthetic transactions 相关公开说明：用于理解反洗钱合成交易数据字段和业务语义。

项目的业务主题、目录结构、事件模型、风控规则、Flink 作业、README 和文档均按 FinGuard 支付风控场景重新设计。
