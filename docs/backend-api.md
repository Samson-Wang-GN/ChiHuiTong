# 后端接口与角色接入约定

适用：需求0.32、REQ-043；2026-09-12。本文描述已实现后端，不表示旧原型已经接入。完整路由以`backend/chihuitong/urls.py`为准；严格输入字段定义在对应`api*.py`的Serializer中，业务最终校验在`services/`。真实第三方配置和用户验收单独跟踪。

## 公共约定

REQ-045补充：完整Web界面位于`backend/chihuitong/acceptance_assets/`，受保护验收代理前缀为`/chihuitong`，浏览器以`X-CHT-Authorization`传业务Bearer，由专属代理转为标准Authorization，避免覆盖第一层访问保护。通用列表支持白名单`ordering`（减号表示倒序），不支持任意关联字段排序。`GET /files/{id}/details`返回同一访问边界内的附件名、类型、大小，不返回存储路径。`POST /clinics/map-preview`接受门诊ID（新建时可省）、经纬度和缩放3～18，返回固定600×360 PNG；缺Key不返回虚构地图。通知中的`contract_version_id`指向当前可查看合同版本，合同明细仍独立校验权限。

`GET /payments/configuration`告知是否启用显式模拟；仅非生产独立验收允许。用户本期明确要求真实微信调用和短信发送为空壳模拟成功，模拟记录不能等同于真实到账/送达。实际规则与保护见ADR-0028。

- Web前缀`/api/v1`，JSON请求；上传为multipart，字段`file`及`purpose`。不接受未知字段或非对象JSON。
- 先`POST /auth/code`提交`phone`，再`POST /auth/login`提交`phone/code`。成功返回不透明token和机构身份；业务请求同时携带`Authorization: Bearer <token>`、`X-Membership-ID: <membership UUID>`。一个手机号可有多个机构身份，客户端明确选择，不把手机号当租户。
- `GET /auth/me`列当前可用身份；`POST /auth/logout`撤销当前会话。停用账号、身份或机构后下一次请求立即拒绝。平台初始账号通过服务器交互命令创建，不提供公开自注册后台管理员。
- 小程序共用业务后端但登录受众分离，见下文；Web token不能用于小程序，也不能反向使用。
- 关键写入要求`Idempotency-Key`（8～128字符，同一动作重试复用）；相同键不同内容409。需要版本的写入传`version`，旧版本409后重新读取；不能盲目以新键重复付款。写入所需`reason/confirmed`不可省略。普通审核/配置使用版本与数据库约束防重，精确输入见Serializer。
- 金额用整数分（`*_cents`），比例为十进制定点数，四舍五入；前端不能提交可信分配结果。所有对象UUID，客户另有自动生成且稳定的`number`；资源方客户编号只留存。
- 时间为带时区ISO8601，日期`YYYY-MM-DD`；业务按北京时间计算，付款3/5自然日从出账次日起算。枚举使用英文稳定值，中文显示由前端映射，不能通过改中文显示推断业务状态。
- 通用列表`page/page_size/status`，页大小1～100；返回`results/total/counts/page/page_size`。`counts`基于相同权限及筛选、尚未按状态缩窄的记录；`all`总数用于状态Tab。工作台使用`pending/processed`。客户附近门诊是搜索结果，不展示内部审核Tab。
- 业务错误含`code/message/details/request_id`；格式/框架错误含`code/details/request_id`。400输入错误、401未登录/会话失效、403身份或功能不允许、404不存在或无权知道、409版本/状态冲突、429限流、503外部配置/服务不可用。所有响应含`X-Request-ID`，日志仅记追踪ID与错误类别，不记录原始请求、手机号、验证码或支付报文。
- Excel下载为当前权限、当前筛选的全部数据，不只当前页；转义公式注入。私有附件按关联对象再次鉴权，禁止使用静态公网存储地址读取。来源方可见本人来源客户手机号，其他后台按业务授权脱敏；门诊预约联系人手机号可见。

## 四角色边界

| 角色 | 数据范围 | 主要操作 |
| --- | --- | --- |
| 平台管理员 | 平台业务资料 | 机构及管理员、来源名、产品、合同和分配、资质审核、门诊上下线/渠道变更、订单审核/收款、合作方付款、短信/日历/异常任务 |
| 客户资源方管理员 | 本机构全部订单及下游客户权益/预约/核销，整张本机构结算单 | 销售订单、Excel、采购付款凭证、取消/停止申请、整单确认/确认收款、机构账号 |
| 客户资源方业务员 | 自己负责的销售订单及其下游 | 本人销售业务及明细；不能处理或读取整张机构结算单 |
| 门诊渠道管理员 | 本机构全部门诊、合同及账单明细，自己机构结算单 | 门诊建档/资料变更、三方合同签订续签、门诊产品上下线、催收、机构结算确认/收款、账号 |
| 门诊渠道业务员 | 自己负责的门诊及其相关明细 | 同范围门诊业务/催收；不能确认预约或核销，不能处理机构整单 |
| 门诊管理员 | 本门诊 | 预约履约、资料变更、产品、账单付款、合同查询、账号 |
| 门诊员工 | 本门诊预约及履约工作 | 确认/改期/核销/补核销/未结算撤销；不能处理合同、账单或账户管理 |

机构管理员不实现任意功能权限编辑；业务员负责人仅落订单/门诊主对象，下游关联读取，不复制归属，交接功能本期不开发。平台创建的首管理员角色不可被机构管理员修改。

## 公共和平台管理

| 对象 | 主要相对路径 | 行为 |
| --- | --- | --- |
| 机构与账号 | `/organizations`、`/{org}/review/resubmit/status`、`/{org}/members`、`/members/{id}` | 创建、查询、审核、停用及两类账号；真实路径中机构ID紧跟`organizations/` |
| 产品 | `/products`、`/products/{id}` | 内/外名称、使用规则、一次核销份数和获客费、启停及修订 |
| 来源展示名 | `/organizations/{org}/source-brands` | 平台配置机构专属列表；资源方只选本机构来源 |
| 合作信息 | `/organizations/{org}/cooperation` | 当前/下一/待审核合同及历史、可用产品入口，机构只读 |
| 合同版本 | `/organizations/{org}/contracts`、`/contract-versions/{id}`及`submit/review/terminate/products`子路径 | 草稿、提交、平台审核、终止、同合同多产品分配；新业务只用当前有效版 |
| 门诊 | `/clinics`、`/clinics/{id}`、其`profile-changes/service-status/confirmation-hours/channel/products` | 资料变更保留已生效版本、审核后更新；上下线独立操作且记原因；时限仅平台可改 |
| 定位 | `/clinics/geocode` | 地址解析候选、精度提示；必须地图确认并随资料审核，不能自动覆盖生效坐标 |
| 附件 | `/files`、`/files/{id}` | 上传与授权下载；用途cover/license/contract/payment/sales_excel |
| 审计 | `/objects/{object_type}/{id}/logs` | 门诊、合同、账单、预约等按对象授权，只读不可变操作记录 |

合同分配按核销时的当前渠道和适用合同锁定。比例/固定金额组合不能超过获客费，包括已批准未来条款；新产品条款、合同审核、获客费变更均验证。历史交易不随新比例重算。

## 客户资源方销售与Excel

1. `POST /sales-orders`选择`physical/named`、产品、来源、数量、单卡采购价、负责人；记名单客或关联已确认Excel。创建者默认负责人。零价待审核；有价先上传采购付款凭证、平台确认足额到账。
2. `GET /sales-orders/{id}`含流程、号段、任务错误/重试状态、来源及产品快照。`rows/cards`子路径分页；`cards/export`导出权限范围卡明细。卡凭证与患者身份不进入日志。
3. `POST /sales-orders/{id}/receipts`提交真实线下凭证；`POST /purchase-receipts/{id}/review`平台审核。`POST /sales-orders/{id}/review`平台开卡审核，超过500张返回处理中，后台事务开卡，失败不产生半批权益。`stop/stop-review/refund/shipment`执行申请、平台处理、线下退款登记和寄送登记；取消/停止类型由请求明确，已激活整批不取消。
4. Excel先`POST /files`上传，`POST /imports`发起解析；轮询`GET /imports/{id}`。`suggest`给列建议，`mapping`保存人工确认列及数量策略，异步逐行校验，`rows/errors.xlsx`查异常/下载，`confirm`冻结通过的导入依据供销售订单使用。格式模板`/import-formats`只存列结构，不存客户样本。
5. 只认可姓名、规范化手机号和数量，性别/年龄/职业可选且只补空；资源方客户编号保留原值。姓名冲突及重复行有明确异常，开卡审核再次检查当前数据库，不按导入预览强制覆盖。
6. `POST /cards/{id}/freeze`平台冻结/解除冻结；已激活卡不转让。停止仅失效未领取部分，已领取不伪回滚。所有卡号段全局唯一，取消后不复用。

## 门诊预约与履约

- `/appointments`及`/{id}`返回角色可见明细，含门诊结算情况；`export.xlsx`同范围导出。门诊在`/{id}/confirm/cancel/reschedule`处理确认、无法接诊及协商改期；渠道不得代办。输入结构及动作枚举见`api_appointments.py`。
- `/reschedules`、`/{id}/review`处理客户发起的改期；确认前保留原预约时间，改期不得超过权益到期日。客户手机号可供预约门诊联系。
- `/redemptions/scan`解析固定卡二维码得到待履约预约；`/redemptions/quote`返回短期签名费用报价；`POST /redemptions`提交预约、凭证、版本、确认及报价令牌。最终服务端重新锁定校验费用，客户端不能传获客费结果。
- `/redemptions/{id}/reverse`只撤销未结算且无未决支付/待审收款的交易。普通撤销恢复成功预约和占用；系统自动完成后的补核销撤销恢复系统完成，权益待客户申请恢复，不生成门诊待办。
- `/fulfillment-tasks`为过期预约待办：24小时生成，72小时系统完成不核销、不收费、不释放；客户确认未到才恢复，确认已到给门诊补核销待办。争议仅记录，不实现平台裁决流程。
- `/appointments/reminder-snapshot`提供完整待确认记录ID/版本/数量和摘要。建议5秒轮询，重连读取完整快照；关闭提醒窗不是确认预约。浮窗UI本期不动。

## 账单与支付

- 门诊账单`/clinic-bills`，详情`/{id}`、`lines/export.xlsx/receipts/feedback/collection-note/payments`。周一/每月1日由任务出账，未出账交易随新账期，既有账单不追溯；逾期只提醒，不自动下线。
- `POST /clinic-bills/{id}/receipts`提交付款金额、时间、付款方、流水和附件；`POST /clinic-receipts/{id}/review`平台确认到账。实收全额才整体冲销有效交易，部分款不提前进入合作方分账。
- Web `POST /clinic-bills/{id}/payments`传`version/method=native`和幂等键，202返回`creating/pending/unknown/success/closed`状态。仅pending且未过期才有付款参数；不得按二维码展示或客户端提示标记收款。
- `POST /payments/{id}/query/close/retry`均须`confirmed=true`。未知创建可用同商户单号重试准备，不能跳过查单关闭另建支付。可信成功到账去重后结清；晚到/重复/版本异常资金保留核对记录，不丢弃真实收款。
- `/payments/wechat/notify`唯一公开支付回调：验签解密、订单/商户/金额校验、持久化后异步入账；无签名不接受。生产微信缺配置503，不用模拟替代。
- 合作方`/partner-bills`仅资源方和渠道方，没有平台作为收款方的第三张单。月度汇集截止时已收到门诊款且本方历史未结算的交易；`/{id}/lines/export.xlsx`完整明细。`confirm → pay → receive`分别合作方管理员、平台付款登记及凭证、合作方管理员确认收款；0元`no_payment`直接终态，不走付款/确认。
- 业务员仅`/settlement-details`及`/settlement-details/export.xlsx`本人明细，不返回整单总额。`/finance-feedback/{id}/respond`平台回复；合作方待确认异议处理后需重新确认；普通门诊反馈不改变金额版本，不阻断付款。

## 工作台、指标及运维

- 每个角色`/workbench`和独立`/workbench/tasks`按权限返回待办，`/{category}/{id}`给具体业务记录和允许操作。任务状态随真实业务变化，阅读/通知已读不自动完成任务；返回的`detail_endpoint`属于当前登录端。
- `/notifications`、`/{id}/read`为本人站内通知。平台`/sms-templates`配置预置模板、`/sms-deliveries`及`/{id}/attempts`查每次发送证据；服务商接受不等于手机已送达。`/jobs`及`/{id}/retry`查看和重试失败任务，不暴露加密载荷。
- `/calendar`与`/calendar/{date}`平台维护工作日，审核2工作日和提醒用此日历；付款期限不依赖工作日。
- 平台/资源方`/customer-overview`及`products/trend/details/customer-cards/export.xlsx`。`date_from/date_to`圈选开卡批次，`as_of/recorded_cutoff`锁观察时点，`resource_id/product_id/mode`按权限筛选；趋势`granularity=day/week/month`、`display=cumulative/net`，比率明细`component=numerator/denominator`。人数跨来源去重、系统完成不计核销，分母0返回null；单次最多366点。历史资料标签为当前授权资料，不冒充历史姓名。

## 小程序共用后端（未修改两个小程序UI）

- 独立前缀`/api/v1/mini/customer`和`/api/v1/mini/clinic`，各自`POST /login`传`login_code/phone_code`，由微信服务端验证OpenID及手机号code对应关系。不接受客户端自报手机号/OpenID；手机号目前不支持真实变更。门诊必须已经开通员工身份；客户可先授权手机号，预约前补姓名。
- 客户：`me/logout/profile/benefits`、`cards/{id}/claim`、`cards/activate`、`appointments`、`appointments/{id}`及`cancel/reschedule/feedback/restore`、`messages`及`/{id}/read`。权益卡直接返回外部名称、来源和使用规则；预约详情直接返回有效核销二维码。客户只能处理自己的权益和预约。
- 客户门诊搜索`GET /clinics?benefit_id=...&longitude=...&latitude=...`，坐标可整体省略；按有效合同/产品及门诊状态筛选，距离为GCJ-02直线距离。详情`/clinics/{id}`与`/cover`只公开门诊联系/地址/封面；没有本人历史预约时需带本人有效benefit_id。不返回业务联系人、资质或合同附件。
- 门诊身份还必须带`X-Membership-ID`；管理员可读合同账单，员工仅预约。相对路径包含`workbench`、`appointments`、`reschedules`、`redemptions`、`fulfillment-tasks`、`bills`、`organizations/{id}/cooperation`、`notifications/files`及对象日志。
- `POST /mini/clinic/bills/{id}/payment`仅门诊管理员，提交账单version及幂等键。服务端用已验证的当前门诊AppID/OpenID产生JSAPI参数，不允许上传付款人OpenID。`/bills/{id}/receipts`支持上传线下凭证。真实支付须等商户和AppID授权齐备后真机验收。

## 版本和验证限制

接口开发及服务器模拟测试不代表前端已联通、不代表短信已送达/地图已开通/微信真实收款。测试证据与尚待完成综合项见[实施清单](backend-plan.md)。身份、医疗资料、资金变更在生产发布前仍须非作者安全评审及用户验收。
