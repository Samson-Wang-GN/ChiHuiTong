# 齿慧通

“齿慧通”是连接客户资源方、口腔门诊渠道公司、口腔门诊和终端客户的口腔福利履约与门诊获客平台。客户资源方可以购买并投放不记名权益卡，或通过记名非实体卡销售以Excel批量/后台单客录入客户及数量；客户扫码激活不记名卡，或注册绑定后领取 Excel 已分配权益，再通过“附近门诊—意向预约—门诊确认—到诊扫码—核销”闭环使用福利。每笔权益保留独立来源归属，当前不判断或统计“新客”。

当前进入开发准备阶段，正式后端技术栈及业务实现尚未启动。本地维护Git并与[GitHub仓库](https://github.com/Samson-Wang-GN/ChiHuiTong)同步；公共开发服务器只接收文件、不运行GitHub同步。所有测试只能在公共开发服务器140.143.125.233执行，详见[开发环境与同步流程](docs/operations/development.md)。

已进入后台原型评审阶段：四组原型分别位于 `prototypes/platform/index.html`、`prototypes/resource/index.html`、`prototypes/channel/index.html`、`prototypes/clinic/index.html`。所有依赖已随项目保存；只在指定服务器上运行和验证。详细入口和评审说明见 [后台原型说明](docs/prototype-review.md)。

服务器测试入口由 `scripts/run_remote_tests.py` 在服务器本机127.0.0.1:8765临时启动，测试结束关闭。以下历史localhost链接表示测试服务器内的页面地址；不再在本地电脑启动原型或运行浏览器测试，也不开放新的公网端口。

产品入口包括独立的客户端微信小程序、独立的门诊端微信小程序，以及客户资源方、门诊渠道公司和门诊使用的多角色后台系统。两个小程序共享服务端业务数据和安全规则，但入口、登录态、界面和权限相互分离；同一手机号可以分别具有客户和门诊员工身份。

两个移动交互原型已独立交付：[客户端](prototypes/customer-mini/index.html)、[门诊端](prototypes/clinic-mini/index.html)。启动上述服务后分别访问 `http://127.0.0.1:8765/customer-mini/` 和 `http://127.0.0.1:8765/clinic-mini/`。这是浏览器原型，不是已发布的微信小程序；当前各组演示数据和登录态独立，不进行跨端同步。页面清单、演示卡号及操作步骤见 [小程序原型评审](docs/mini-program-prototype-review.md)。

## 当前状态

- 0.30开发准备：本地Git → GitHub；本地提交归档 → 公共开发服务器独立版本目录 → 服务器测试副本。首次同步和验证结果记录在[任务](docs/tasks.md)，开发与测试不使用齿慧/Study System现有业务数据。

- 需求0.29.2已落地：门诊主动登录默认开启紧凑预约提醒窗，工作台保留“开启预约提醒”，新预约自动变色/更新数量，人工展开和收起。详见[REQ-039](docs/requirements.md#req-039-门诊预约确认提醒小窗0292已确认)。本轮仅文档，原型尚未同步这套交互；下方0.29.1仍为手动开启大窗试用，后续任务TASK-068/069。

- 0.29.1门诊悬浮工作台试用：打开 [门诊后台](http://127.0.0.1:8765/clinic/)，点击“开启悬浮工作台”，再点“5秒后模拟新预约”并切换Tab。真实Document Picture-in-Picture窗口，非页内仿制；需支持此能力的桌面浏览器，原型仅模拟预约、不接真实推送。详见[试用说明](docs/prototype-review.md#0291门诊悬浮工作台试用)。

- 需求已更新0.29：核销时锁费/分配，按有效预约日校验权益，平台人工处理逾期上下线、已结算禁止撤销、未结算撤销移除账单有效交易、合同账期立即生效不改已出账、后台验证码/小程序手机号授权，以及特殊补核销撤销。整单仅机构管理员处理，业务员看本人明细；交接功能延期至上线后考虑，本期仅保留[负责关系与历史数据解耦约束](docs/requirements.md#req-038-业务员交接延期与数据设计约束已确认)。期限已确认为自然日、出账次日起算；特殊撤销的权益先转待恢复，客户申请后才释放。
- **运行原型已同步0.29**：未出账按新账期归集、分配四舍五入至分；新增账期变更/归集演示、业务员本人结算明细、手机号验证码登录、核销费用快照、未结算账单修订及客户待恢复申请。专项：`python -X utf8 prototypes/verify_rules29.py`。详见两份原型评审；无真实资金操作、交接或跨角色数据同步。

- 已建立项目级开发规范和软件管理流程。
- 已形成业务角色、核心流程、权限边界和功能需求清单初稿。
- 需求及原型已同步0.28（2026-09-09）：门诊小程序管理员专属合同、账单与付款，员工保留预约核销履约；门诊账号角色统一管理员/员工；客户权益卡显示规则直达预约，预约详情直接展示关联固定码。专项：`python -X utf8 prototypes/verify_mobile_access.py`。真实微信支付和跨端同步未接入。保留0.27（2026-09-09）：资源方/渠道区分管理员和业务员、按关联范围展示；新增机构同时登记锁定角色的首管理员；平台门诊列表上线/下线原因弹窗，门诊及账单/采购订单详情统一操作记录。未知归属不开放；混合账单仅展示业务员本人明细，真实权限和跨端日志未接入。保留0.26：门诊/渠道不可编辑待确认时限；已审核门诊所有资料修改提交平台变更审核，批准才整版生效，退回保持原资料；平台任务页可对照新旧资料及全部附件。保留0.25.1：渠道新增/编辑均可维护展示图及定位；定位采用地图点击/拖动标记/缩放后确认，坐标自动回填只读（本地虚构示意图，非真实地图）。保留0.25：新增渠道/门诊共用资料维护、单张小程序展示图片、前台预约手机号、业务联系人/电话和地址定位核对演示；真实地理编码及小程序同步未接入。保留0.24.1：平台机构管理采用与门诊一致的列表“详情”→右侧抽屉交互，内含“机构资料 / 合作合同 / 推广产品配置”，移除两个独立合同菜单，机构内登记审核及多产品分配；门诊三方合同仍在门诊管理。保留0.23：过期预约24小时待办、72小时系统完成不核销/不释放/不计费；门诊报未到取消但保留权益，客户未到申请自动恢复或已到转新补核销待办。保留0.22：平台/资源方分别提供客户与权益概览、产品指标、日周月趋势、明细和Excel；同角色已审核销售卡可汇入，只读且无跨角色同步。保留0.21统一“推广产品销售”，资源方填写采购价（默认0元），非零须全额到账后平台审核开卡，实体卡自动登记号段；保留0.20补齐合作方收款确认、仅已回款历史未入单交易的月度归集、预约门诊结算状态；保留逐笔对账与真实Excel下载、合作方确认后平台登记付款及凭证、推广产品内外双名称、四角色独立任务页；保留0.18去授信、周/月账单和门诊三方合同。
- 四组39个后台业务页、两组39个移动场景；验证说明及入口见原型评审文档。真实支付、跨端数据及后端权限未接入，MVP冻结及详细权限仍待评审。机构身份与日志专项：`python -X utf8 prototypes/verify_management.py`；资料变更审核专项：`python -X utf8 prototypes/verify_clinic_review.py`；资料定位专项：`python -X utf8 prototypes/verify_clinic_info.py`；机构整合专项：`python -X utf8 prototypes/verify_institutions.py`；过期预约专项：`python -X utf8 prototypes/verify_overdue.py`；分析专项：`python -X utf8 prototypes/verify_overview.py`；销售专项：`python -X utf8 prototypes/verify_sales.py`；收款及归集专项：`python -X utf8 prototypes/verify_settlement.py`；已有专项命令：`python -X utf8 prototypes/verify_operations.py`；先启动上述8765本地服务。

## 文档入口

- [项目开发规则](AGENTS.md)
- [软件开发与管理规范](docs/development-management.md)
- [产品需求](docs/requirements.md)
- [Arco Design 项目设计要求](docs/design-requirements.md)
- [后台原型与评审说明](docs/prototype-review.md)
- [小程序移动设计要求](docs/mini-program-design.md)
- [两个小程序原型与评审说明](docs/mini-program-prototype-review.md)
- [系统架构](docs/architecture.md)
- [任务计划](docs/tasks.md)
- [技术决策](docs/decisions/README.md)

## 开发与运行

先阅读 `AGENTS.md` 及[开发环境](docs/operations/development.md)。本地提交后执行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync-development.ps1` 上传无Git元数据的快照；登录指定服务器后执行 `/home/ubuntu/ChiHuiTong/.venv/bin/python /home/ubuntu/ChiHuiTong/current/scripts/run_remote_tests.py --suite all`。Bypass只对本次脚本进程生效，不改全局策略。测试脚本拒绝非目标主机执行，并将逐项日志/截图保存到服务器test-results目录。正式后端技术栈、应用环境变量、CI和生产部署待后续设计，不以静态原型代替。

## 安全提示

仓库不得存放真实患者数据、生产密钥、密码、Token、Cookie 或私钥。后续新增环境变量时，应同步维护 `.env.example`，但只能提供安全的占位值。
