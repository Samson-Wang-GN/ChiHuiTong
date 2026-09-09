# 开发环境与文件同步

- 状态：0.30开发准备；2026-09-09
- 关联：REQ-040、TASK-070～072、ADR-0019

## 固定边界

| 用途 | 位置 | 职责 |
| --- | --- | --- |
| 本地Git工作仓库 | `D:\My work\ChiHuiTong` | 编辑、静态检查、commit/fetch/push；唯一与GitHub同步的位置 |
| GitHub | `Samson-Wang-GN/ChiHuiTong` | 版本留存，默认主分支main；不配置托管Runner执行测试 |
| 公共开发测试服务器 | `ubuntu@140.143.125.233` / `VM-0-12-ubuntu` | 文件快照与全部测试，禁止为本项目clone/pull/push |
| 项目根 | `/home/ubuntu/ChiHuiTong` | 独立于齿慧公共服务和Study System，权限0700 |
| 版本及当前快照 | `releases/<完整提交号>` / `current` | 无`.git`的提交文件，current为可回退的软链接 |
| 测试环境 | `.venv` | 项目独立Python环境，Playwright固定1.58.0 |
| 测试产物 | `test-results/<UTC时间>-<提交号前缀>` | 独立workspace、各脚本日志、截图及summary.json，不回写交付快照 |
| 传输包 | `incoming/` | 本地git archive生成的文件包及SHA-256，保留此前版本指针 |

SSH使用已有专用私钥 `C:\Users\Admin1\.ssh\genius_server.pem`；只记录路径，私钥内容不得复制至项目或服务器。强制已有主机公钥校验与BatchMode，不用跳过主机校验的临时连接。地址源自齿慧开发公共服务器记录，并现场核对hostname；不使用43.162.110.152应用开发服务器或任何生产服务器。

本次不修改共享服务、Nginx、数据库/Redis、防火墙或GitHub仓库可见性；不开放公网原型地址。静态原型认证仅演示，不适合当成真实业务安全边界。所有测试进程和浏览器均在服务器运行；旧文档的本地命令/截图仅作历史。

## 本地工作流

1. `git status --short`，保留其他人修改；新需求先写需求/任务/必要ADR。
2. 静态检查待提交文件、差异、秘密与大文件。`.env`、密钥、日志、缓存及临时包忽略；Arco/React许可证和原型基线截图保留。
3. 正常提交，不使用`push --mirror`或强推。首次工具提交采用仓库局部作者`Codex <codex@openai.com>`，不修改本机全局Git配置。
4. 本地执行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync-development.ps1`，只打包已提交且工作区干净的HEAD，经过SSH传输和SHA-256核对；服务器不携带Git对象和GitHub凭据。Bypass仅作用于本次进程运行已审查脚本，不更改全局执行策略。该步骤只同步文件，不宣称测试已通过。
5. 在服务器执行测试，成功后本地推送 `git -c http.sslBackend=openssl push -u origin main`，并用`git ls-remote`核对HEAD。首次空仓库初始化使用main；后续采用短分支评审，不覆盖远端更新。Windows当前schannel无法获取凭据时，命令级使用OpenSSL后端，不能关闭TLS校验。
6. 测试修复先落回本地，再提交、重新同步并在服务器重测；不把测试服务器临时改动作为未入Git的交付。文档证据补充产生新提交时重新同步，记录业务代码是否变化。

## 服务器准备和测试

仅在目标服务器项目根首次创建独立环境，不能更改系统Python或其他项目venv：

```bash
python3 -m venv /home/ubuntu/ChiHuiTong/.venv
/home/ubuntu/ChiHuiTong/.venv/bin/python -m pip install -r /home/ubuntu/ChiHuiTong/current/requirements-test.txt
# 只有浏览器包缺失时才需要安装；当前服务器已有对应浏览器缓存。
/home/ubuntu/ChiHuiTong/.venv/bin/python -m playwright install chromium
/home/ubuntu/ChiHuiTong/.venv/bin/python /home/ubuntu/ChiHuiTong/current/scripts/run_remote_tests.py --suite all
```

上述安装使用包源/浏览器分发服务，不使用服务器GitHub仓库同步；下载失败保留错误，可由本地获取依赖包再上传，不能借机复用生产环境或关闭证书校验。不得擅自升级共享系统包。

测试脚本核对Linux主机名和固定版本路径，复制版本后启动仅服务器loopback可见的HTTP进程，顺序执行18个现有脚本；`--suite smoke`仅3个脚本，不能冒称全量通过。8765占用时拒绝启动，不杀死不明进程。日志包括逐脚本退出码、时长及原交付文件校验结果；失败保留完整日志，测试结束关闭本次HTTP服务。

当前测试验证虚构原型，不验证真实支付、短信、跨角色后端同步或生产权限。Linux无头浏览器不能验收Windows原生置顶；用户要求全部测试在服务器，这项仍保留未验收，不转为本地测试。REQ-039新交互尚未实现，不以旧浮窗脚本通过替代。

## 回退与记录

每次保留完整提交快照及归档，切换前记下此前current指向；需要回退时核对目标位于本项目releases下，再切换current到既有版本，不修改GitHub历史或删除预约数据。当前没有数据库迁移、应用服务或资金操作。失败快照、日志不自动清理；后续容量清理需限定对象、保留必要证据后执行。

每次交付记录GitHub提交、服务器current提交、传输摘要、测试报告路径及现有服务状态。仅同步成功、进程存在或服务active均不替代业务测试通过。服务器不提供本项目Git镜像。
