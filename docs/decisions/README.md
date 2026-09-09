# 技术决策记录（ADR）

本目录记录会长期影响系统的技术决策，例如技术栈、系统边界、数据模型、认证授权、外部集成、部署和关键依赖。

## 命名

本轮决策：[ADR-0019 本地Git与公共服务器测试](0019-local-git-remote-testing.md)。

历史提议：[ADR-0015 业务员负责关系交接](0015-responsibility-handover-proposal.md)，功能已延期至上线后；本期仅保留REQ-038解耦约束。

本轮决策：[ADR-0018 门诊预约提醒生命周期](0018-clinic-appointment-reminder-lifecycle.md)，已接受设计，尚未实现。

上一轮决策：[ADR-0017 门诊悬浮工作台试用](0017-clinic-document-pip-prototype.md)，保留0.29.1历史验证。

上一轮决策：[ADR-0016 核销与结算规则](0016-redemption-and-billing-rules.md)。

上一轮决策：[ADR-0014 移动身份、付款与固定凭证](0014-mobile-identities-payment-credential.md)。

上一轮决策：[ADR-0013 机构身份与对象日志](0013-institution-identities-object-logs.md)。

上一轮决策：[ADR-0012 门诊生效资料与变更审核](0012-clinic-profile-change-review.md)。

上一轮决策：[ADR-0011 门诊资料与地址坐标确认](0011-clinic-profile-location.md)。

上一轮决策：[ADR-0010 平台机构内合同与推广产品配置](0010-institution-contract-product-workspace.md)。

上一轮决策：[ADR-0009 预约自动完成与真实核销分离](0009-overdue-appointment-completion.md)。

上一轮决策：[ADR-0008 客户权益分析与时点统计](0008-customer-benefit-overview.md)。

上一轮决策：[ADR-0007 推广产品销售统一订单](0007-unified-product-sales.md)。

既有决策：[ADR-0006 对账付款、推广产品与任务聚合](0006-statements-products-tasks.md)。

使用四位递增编号：`0001-short-title.md`。

## 状态

`提议`、`已接受`、`已拒绝`、`已替代`。已接受的决策发生变化时新增 ADR，并在新旧文件中记录替代关系，不直接抹去历史原因。

## 模板

```markdown
# ADR-0001 决策标题

- 状态：提议
- 日期：YYYY-MM-DD
- 关联需求：REQ-xxx

## 背景

要解决的问题、约束和已知事实。

## 备选方案

各方案及其优点、代价和风险。

## 决定

选择的方案及选择原因。

## 后果

正面影响、负面影响、迁移和后续工作。

## 验证与复审

如何验证决定有效，以及何时需要重新评估。
```
