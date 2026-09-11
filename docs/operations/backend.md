# 后端开发测试与运维交接

2026-09-12，REQ-043。所有验证只在`ubuntu@140.143.125.233`执行。本地编辑、静态检查和Git；服务器不创建`.git`、不连接GitHub。没有新增公网入口或修改共享服务。

## 隔离布局

| 内容 | `/home/ubuntu/ChiHuiTong/`下的位置 |
| --- | --- |
| 提交快照 | `releases/<40位提交>`，`current`指向当前版本 |
| 后端依赖 | `.venv-backend`，Python3.12、pip26.2.1，直接/传递依赖固定版本 |
| 审计工具 | `.venv-audit`，独立于后端依赖 |
| PostgreSQL16 | `runtime/postgres`，Unix socket `runtime/pgsocket`，端口参数55432、`listen_addresses=''`，无TCP监听 |
| 测试密钥 | `runtime/backend-test-secrets.json`，随机生成、0600、不打印、不提交、不复制到生产 |
| 测试产物 | `test-results/<UTC时间>-<提交前12位>-backend`，workspace副本、private-files、逐步日志、summary与coverage |

`chihuitong_dev`为本项目开发迁移库；`test_chihuitong`每轮重建/销毁。测试仅合成资料。原型`.venv`、齿慧公共服务、Study System、共享Nginx/Redis/数据库及防火墙均不改。

## 验证和交付

本地提交后用`scripts/sync-development.ps1`按SHA-256经SSH同步。在指定服务器执行：

```bash
python3 /home/ubuntu/ChiHuiTong/current/scripts/run_backend_tests.py
python3 /home/ubuntu/ChiHuiTong/current/scripts/audit_backend_dependencies.py
```

运行器依次核对主机/目录、非阻塞锁、独立依赖、lint与格式、迁移无差异、数据库迁移、Django检查、临时WSGI冒烟、合成备份恢复、全量测试及覆盖率。每步单独退出码、15分钟超时；共享服务状态和快照摘要前后相同才通过。不得绕过锁并发重建测试库。

`--generate-migrations --format`只用于开发迭代；取回前核对本地没有更新，优先精确文件，不覆盖未提交改动。最终提交不带这两个参数测试。`--labels`仅专项诊断，不冒称全量。Gunicorn冒烟只绑定服务器127.0.0.1随机端口，结束关闭，不部署永久服务。

通过后本地正常push GitHub，核对GitHub HEAD、服务器current及已测提交；文档追加导致新提交时明确变化并重新验证，不伪造报告归属。

## 启用前配置与命令

`.env.example`不是可用生产配置。正式环境需独立应用/Fernet/HMAC密钥、最小权限数据库账号、私有附件目录、HTTPS及允许域名。配置放源码外0600文件或密钥服务，不进命令参数/日志。微信、短信、地图缺配置默认失败，不能降级模拟成功。

另行批准部署并加载私有环境后运行：

```bash
python manage.py migrate --noinput
python manage.py initialize_configuration
python manage.py bootstrap_platform
```

平台首账号交互读取手机且不回显；已有平台拒绝重复初始化。模板初始化不覆盖已有配置且默认不发送。Web采用`gunicorn config.wsgi:application`，实际绑定/TLS/托管由部署审批确定。本次只验证可启动，不开公共入口。

每分钟运行`python manage.py run_worker --limit 100`，先扫描到期业务再领取任务。任务有租约和随机领取令牌，旧worker不能覆盖新领取结果。扩大并行数先做容量评估。

## 每日核查

- 查看失败任务、短信尝试、未决支付、待审凭证、到期合同及逾期账单；不能直接修改数据库“修复”资金。
- 短信报备、费用和失败重试由平台负责；服务商接受不等于手机收到。联系人填座机会发送失败，需核实可收短信的号码，不自动改发其他私人手机号。
- 日历初始仅周末，节假日/调休平台维护；付款3/5天为自然日、出账次日起算。
- 预约提醒使用鉴权5秒快照；阅读通知/关闭窗口不等于处理预约。浮窗UI本次不改。
- 周一/每月1日出账，历史未归集交易保留。若整个出账日停机，平台须核查并经审计安排补账或下期归集；当前不自动伪造历史出账事实。逾期不自动上下线，存量确认预约继续履约。
- 极端0获客费门诊单为`no_payment`，没有实际收款事实，暂不自动满足合作方已回款归集条件；正获客费但某方分配0元，回款后正常生成该方0元单。这项工程默认供用户审阅。

## 备份恢复与回退

备份必须包含数据库及加密附件，解密/HMAC密钥独立保管；只存dump不能恢复全部资料。字段密钥环支持新钥写入、旧钥读取；HMAC索引密钥不可直接替换，须专项迁移，否则手机号关联失效。

`verify_backup_restore`只在独立实例新建两个随机命名合成库：全迁移、合成客户密文、PG16 `pg_dump`/`pg_restore --single-transaction`恢复至新库、解密及审计触发器检查，并验证合成加密附件恢复。仅删除本次创建的临时库，备份/证据保留，不覆盖已有库；不替代生产备份授权、异地恢复或RPO/RTO评审。

上线前落实备份频率、异地加密存储、留存期、负责人和恢复演练；数据库与附件须有一致性恢复时点。测试报告及未引用上传附件当前不自动清理，未来必须按明确保留范围和引用检查清理，不直接删除目录。

代码回退仅切换已校验release；有数据库迁移时不能仅切代码假称回退。优先兼容迁移及向前修复；破坏性迁移、停写、生产恢复需另行授权/备份/审计。本次没有生产发布。

## 验证限制

证据见[实施清单](../backend-plan.md)。真实PG事务/约束/审计、临时WSGI启动、合成恢复已纳入验证；微信/SMS/地图为模拟契约，未真实收付、短信送达、真机弹窗或前端联调。依赖扫描只覆盖当时已知漏洞，不等于渗透测试。身份、医疗资料、资金和迁移上线前仍须非作者安全评审及用户验收。
