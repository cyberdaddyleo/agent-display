# live/ — crypto-agent 跨机实况采集器（agent-live/2）

给「Agent 战术大屏」(`C:\dsh\agent-display`) 的三主题实况条 / 任务流 / token / metrics 提供真实数据源：
采集 **WIN / MAC / SG / HK** 四节点只读状态 + 真实 token 用量 + 12 个 agent 状态 + 16 条真实事件，
原子写出 `C:\dsh\agent-display\live.json`，页面每 15s fetch 一次。

- 写作用域：`C:\dsh\agent-display\live\` 与 `C:\dsh\agent-display\live.json`；不改 `index.html` / 根 `README.md` / `CHANGELOG.md`，不 git commit/push。
- 远端（Mac / SG / HK）**只读**：探针源码经 ssh stdin 管道送入远端内存执行，不在远端落任何文件、不改远端配置。
- **计划任务**：本轮（2026-10-21 爸爸四令之①）本项目允许自启，已创建 `AGENT_DISPLAY_LIVE` / `AGENT_DISPLAY_SERVER` 两个 AtLogOn 任务（见 §2）。旧项目的"禁止计划任务"禁令不适用于本项目。
- 真实主机与密钥路径**不进公开仓库**：部署配置放 `live/local.json`（已 gitignore），代码只读该文件。

---

## 1. 架构（v2：Win 直连三路，不再经 Mac 中转）

```
Win (<win-host>, 采集器 + live.json)
 ├─ 本地进程内         → C:\research / C:\crypto-agent / Win DSH token 缓存
 ├─ ssh 直连 Mac  15s  → probes/mac_probe.py   (python3 -)
 ├─ ssh 直连 SG   常驻 → probes/sg_probe.py    (python3 -)   ← 见下「SG 常驻会话」
 └─ ssh 直连 HK   12s  → probes/hk_probe.py    (python3 -)
```

- **v1 的 Mac 中转 relay 已废弃**：`probes/relay_probe.template.py` 仅作 v1 遗留保留，v2 运行时不加载。
- **SG 常驻会话（v2 关键）**：实测 Win→SG 单次 SSH 握手 3~8s（同一网络 Mac→SG 也要 2.7~3.8s，属 SG 侧固定成本），
  每 15s 重连会让探针在 6.5~12s 间抖动甚至超时。v2 改为常驻一条
  `ssh root@<sg> "python3 -u -c <守护进程>"` 会话：逐轮把探针源码（base64）经 stdin 送入远端内存执行。
  - 仍是 Win 直连 SG，不落远端文件；单轮读超时仍独立（默认 22s，可用 `local.json` 的 `sg_timeout` 覆盖）。
  - 会话断开/超时后下一轮自动重建（重建轮约 8s，之后约 3~4s）。
  - 远端守护进程 120s 无请求自动退出，避免残留。
- 三路并行（`ThreadPoolExecutor`），任一路失败只降级该节点；总耗时正常 4~6s，重建轮 <10s。

### 部署配置 `live/local.json`（gitignored，不入公开仓库）

```json
{
  "mac_host": "user@mac-host",  "mac_key": "C:\\Users\\<user>\\.ssh\\xiaoma_mac", "mac_timeout": 15,
  "sg_host":  "root@sg-host",   "sg_key":  "C:\\ob\\server-access\\...\\sg.pem",  "sg_timeout": 22,
  "hk_host":  "root@hk-host",   "hk_key":  "C:\\ob\\server-access\\...\\sui.pem", "hk_timeout": 12,
  "note": "本机部署配置；真实值仅存本机"
}
```
缺字段时用代码内默认值（不含真实主机）。换机/换密钥只改 `local.json`，不改代码。

### 密钥与 ACL（Windows OpenSSH 对私钥权限敏感）

```powershell
# SG / HK 私钥（从 Mac 取来后必须收紧 ACL，否则报 bad permissions）
icacls <keys-dir>\\sg.pem  /inheritance:r /grant:r "$env:USERNAME:F"
icacls <keys-dir>\\sui.pem /inheritance:r /grant:r "$env:USERNAME:F"
# Mac 私钥
icacls $env:USERPROFILE\.ssh\xiaoma_mac /inheritance:r /grant:r "$env:USERNAME:F"
```

### 已知坑：known_hosts 主机键变更

服务器重建/IP 复用后，Win `known_hosts` 里的旧主机键会触发 `REMOTE HOST IDENTIFICATION HAS CHANGED`，
采集器里表现为 SG/HK `SSH 连接失败`。处理：先与 Mac 侧可信连接比对指纹，再替换该 IP 的三类键
（ed25519/ecdsa/rsa），备份 `known_hosts.bak-YYYYMMDD-*`。2026-10-21 已实测比对一致后替换。

---

## 2. 启动 / 停止（手工）

```powershell
$py = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe'

# 采一次（默认 --once，约 4~8s），写 live.json
& $py C:\dsh\agent-display\live\collect_live.py

# 常驻循环：每 15s 一次（固定节拍，按采集开始时间对齐）
$env:PYTHONUTF8 = '1'
& $py C:\dsh\agent-display\live\collect_live.py --loop 15

# 校验 live.json 是否符合 agent-live/2 契约（PASS/FAIL + 逐项不符）
& $py C:\dsh\agent-display\live\validate_live.py
```

`--loop SEC` = **采集开始时刻的最小间隔**：单次耗时 5s、SEC=15 时下一轮仍在 15s 后开始，不会漂成 20s；
单次异常慢时至少间隔 1s，避免打满。

### 计划任务（自启，已创建并实测）

| 任务名 | 动作 | 触发/设置 |
|---|---|---|
| `AGENT_DISPLAY_LIVE` | `cmd.exe /c C:\dsh\agent-display\live\run_collector.cmd`（→ 设 `PYTHONUTF8=1`、cd live、单体互斥清理、`python collect_live.py --loop 15`，stdout→NUL、stderr→`collector.stderr.log`） | AtLogOn(Administrator)、InteractiveToken/最高权限、失败重试 99 次×1 分钟、无时长限制（PT0S）、IgnoreNew |
| `AGENT_DISPLAY_SERVER` | `python.exe -m http.server 8123 --bind 0.0.0.0 --directory C:\dsh\agent-display` | 同上 |

```powershell
# 查看 / 启停 / 禁用自启
Get-ScheduledTask -TaskName 'AGENT_DISPLAY_*' | Format-Table TaskName,State
Start-ScheduledTask -TaskName 'AGENT_DISPLAY_LIVE'      # 或 SERVER
Stop-ScheduledTask  -TaskName 'AGENT_DISPLAY_LIVE'      # 注意：Task Scheduler 只杀 cmd 包装，python 孙进程可能残留
Disable-ScheduledTask -TaskName 'AGENT_DISPLAY_LIVE'    # 停用自启（保留任务）
# 彻底删除（两步）
Unregister-ScheduledTask -TaskName 'AGENT_DISPLAY_LIVE' -Confirm:$false
```

**为什么用 .cmd 包装、错误输出重定向**：
1. `PYTHONUTF8=1`（任务动作本身不能设环境变量）；
2. Task Scheduler 以"无控制台/管道"方式起进程时，裸 python 的 `print()` 可能写满管道缓冲而挂起
   ⇒ 现象是"任务 Running 但 live.json 停更"。v2 把 stdout 重定向到 NUL、stderr 到文件，采集器主日志另写 `collector.log`，不受影响。
3. `ensure_single_collector.ps1` 在启动前清掉命令行含 `collect_live.py` 的残留 python，
   避免"任务重启后两个 --loop 实例同时写 live.json / 各开一条 SG 会话"。

8123 服务：`http://127.0.0.1:8123/index.html`（本机）、`http://<本机IP>:8123/...`（局域网，绑 0.0.0.0）。

---

## 3. 数据契约 `live.json`（schema = `agent-live/2`）

v1 字段（`nodes`/`claims`/`progress`/`alerts`）全部保留；v2 新增 `tokens`/`metrics`/`agents`/`activity`。
字段顺序固定；`nodes` 顺序固定 `win → mac → sg → hk`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema` | str | 固定 `agent-live/2` |
| `ts` / `epoch` | str / int | 本机本地时间 `YYYY-MM-DD HH:MM:SS` / Unix 秒 |
| `collect` | obj | `{ok: bool, took_ms: int, errors: str[]}`；`ok`=errors 为空 |
| `nodes[]` | obj[4] | `{id,label,role,state,f1,f2}`；`state∈ok\|warn\|down\|unknown`；`f1/f2` 各 ≤24 字符 |
| `claims` | obj | `{total,verified,refuted,contested,method,hypothesis,parked}`，来自 Mac `BOARD.md` claim 分布表；Mac 不可达时全 `null` |
| `progress` | obj | `{u1:"59/59 @13:05", commit:"8fa62b6", commit_at:"13:37"}` |
| `tokens` | obj | `{win, mac, total}`，见 §4 |
| `metrics` | obj | `{bars, u1, sg, hk, win, mac}`，见 §5 |
| `agents[]` | obj[12] | 固定 12 条、顺序固定：`collector,aggregate,futures,agent-svc,claims,retrieval,replay,u1-vision,u1-verify,duckdb,backup,research`；`{id,label,zh,where,state,pct,note}`，`note` ≤24 字符 |
| `activity[]` | obj[12-16] | 真实事件（最新在前）：`{id,who,title,state,age_s,at}`；`who∈WIN\|MAC\|SG\|HK`，`state∈done\|run\|warn`，`at`=`HH:MM` |
| `alerts[]` | obj[] | `{level,text}`，`level∈bad\|warn\|info`；可空数组 |

不可达降级：远端不可达时对应节点 `state=down`、`f1="不可达"`、`f2=""`，`collect.ok=false` 且 `errors` 记原因，
**仍然原子写出完整 live.json**。

---

## 4. 真实 token 口径（`tokens`）

数据源：本机/远端 DSH 会话缓存 `~/.dsh/storages/session_projcache/sessions/*.json`，每个 session 的
`record.identity.cwd` + `record.rows.tokenUsage.val.totals` + `record.rows.sessionStats.val`。

| 侧 | 过滤 cwd | 实现 |
|---|---|---|
| `tokens.win` | `C:\keshihua`、`C:\dsh` | 采集器进程内直接读文件（本机 `%USERPROFILE%\.dsh\...`） |
| `tokens.mac` | `/Users/sen/look` | mac_probe.py 里 python3 只读累加，JSON 返回 |
| `tokens.total` | Win + Mac 相加 | `inputTokens / outputTokens / cacheReadTokens / allTokens`，`allTokens`=三类之和 |

两侧明细字段一致：`{sessions,inputTokens,outputTokens,cacheReadTokens,cacheWriteTokens,turns,steps,decodeTokens,llmMs}`。
其中 `inputTokens` = `uncachedInputTokens`；`cacheReadTokens` = 命中缓存的读入 token（数值最大，正常）。
**解析失败降级为 0 并记 `errors`，不影响整体采集**。已实测非 0（2026-10-21 14:26：total all=779.5M，win 693.6M / mac 85.9M）。

---

## 5. `metrics` 数据源（全部真实值，拿不到给 `null`）

| 字段 | 来源 | 说明 |
|---|---|---|
| `bars.m1/m5/m15/h1` | SG `/srv/crypto-agent/data/hot/market.db`（只读 SQLite） | `SELECT interval, COUNT(*), MAX(close_time) FROM bars GROUP BY interval`；进度回调限时，超时→`null` 不阻塞 |
| `u1.symbols/size_mb` | Mac `~/taolunchaijie/u1/` | `full/fetch_manifest.json` 的 symbols 数；`du -sk ~/taolunchaijie/u1` → MiB |
| `u1.checked/matched/at` | Mac `u1/verify_report.json` | summary.checked/matched；at=生成时间 HH:MM |
| `sg.*` | SG `/health`(8710) + `df/free` + `systemctl` | `data_lag_s`/`htf15_lag_s`/`futures_fresh`/`data_fresh`/磁盘/内存/units 5 个 unit 健康数 |
| `hk.*` | HK `du -sk /srv/crypto-agent` + `find -printf %T@` + `df` | 备份体积 MiB / 最新备份年龄秒（`now-latest_mtime`）/ 磁盘 GiB |
| `win.*` | Win `C:\research` | `raw_gb`/`duckdb_gb`（1024 进制 GiB，1 位小数）/`u1_files`=results\u1 文件数/`fapi_files`=C:\research\fapi 文件数 |
| `mac.*` | Mac `~/crypto-agent` | git HEAD/HEAD 时间/dirty 文件数/DSH 是否在跑 |

SG bars 当前为 **ETHUSDT 单品种 7 年历史**（1m≈362.9 万、5m≈72.6 万、15m≈24.2 万、1h≈6 万），随采集增长。
`futures_metrics`（OI/多空比/taker/funding）不在此字段，由 `/health` 的 `futures_lag_s` 反映。

---

## 6. `agents` 状态推导（12 条固定顺序）

| id | where | state/pct 依据 | note 示例 |
|---|---|---|---|
| collector | SG | `/health.data_fresh` + `data_lag_s≤120` | `15s 轮询 · lag 60s` |
| aggregate | SG | `htf_lag_s["15m"]≤1200` | `5m timer · HTF 11m` |
| futures | SG | `/health.futures_fresh` + `crypto-futures` unit Result | `OI 43s · taker 11m` |
| agent-svc | SG | `/health.ok` 且 `errors==0` | `8710 在线 · 166 req` |
| claims | MAC | BOARD total vs SG claim-index 条数（索引落后→warn，pct=索引/总数） | `41 条 · 索引 39` |
| retrieval | MAC | BOARD 任务行 `r0zCvK` 的状态文本（含 ✅ → ok） | `FTS5 + 结构化过滤` |
| replay | MAC | BOARD 任务行 `r1xplE` | `真实数据跑通 1250 点/秒` |
| u1-vision | MAC | u1 符号数（≥500 ok）+ 体积 | `524 符号 · 5.1G` |
| u1-verify | MAC | verify_report matched/checked（pct=比例） | `59/59 一致 · 13:05` |
| duckdb | WIN | `full_verify.json` 行数 + duckdb 体积；duckdb mtime 晚于校验文件=构建中 | `137M 行 · 11.7G` |
| backup | HK | 备份年龄 ≤3600s | `870M · 11m 前` |
| research | WIN | raw 体积 + fapi 文件数 | `raw 4.8G · fapi 1573 件` |

`pct`：健康 100；有 lag/告警按比例降（最低 40）；down=0；unknown=50。`state` 只允许 `ok|warn|down|unknown`。

## 7. `activity` 真实事件来源（12-16 条，最新在前）

每条都能追溯，不编造：

1. **Mac git log 最近 6 条 commit**（`~/crypto-agent`，含 epoch/提交说明）；
2. **Mac BOARD / u1**：BOARD.md mtime、`verify_report.json` 59/59、`full/fetch_manifest.json` 524 符号、`fapi/manifest_metrics.json` 30d 采集；
3. **SG**：collector journal 最新行、`crypto-aggregate.timer` / `crypto-futures.timer` 的 `LastTriggerUSec`、`/health.uptime_s`；
4. **HK**：最新备份文件 mtime；
5. **WIN**：`results/u1/full_verify.json`（DuckDB 全量构建完成）、`aux_load.json`（OI/taker/funding 装载）、`build_manifest_full.json`（523 对 5m 建库）、`C:\research\raw` / `fapi` mtime、`C:\crypto-agent` git log。

## 8. 探针清单（全部只读）

| 探针 | 执行方式 | 采集内容 |
|---|---|---|
| `collect_live.py::win_collect` | 本机进程内 | `C:\research` raw/fapi 体积+文件数、`db\crypto.duckdb`、`results\u1` 文件清单与 full_verify/aux_load/build_manifest_full、`C:\crypto-agent` git、Win token 缓存 |
| `probes/mac_probe.py` | Win→Mac `ssh "python3 -"`，15s | git HEAD/log 6 条/dirty、BOARD claim 全档+任务行+mtime、u1 verify/du/manifest、fapi manifest、Mac token 缓存、DSH 进程 |
| `probes/sg_probe.py` | Win→SG 常驻会话，单轮 22s | `systemctl crypto-*` 5 units、`/health`、bars COUNT、claim-index 状态分布、3 个 timer 最近触发、collector/futures journal 时间、df/free、db 体积 |
| `probes/hk_probe.py` | Win→HK `ssh "python3 -"`，12s | `du -sk /srv/crypto-agent`、最新备份 mtime、`df -k /` |

所有远端探针：源码经 stdin 管道执行，**不在远端落文件**；输出用 `@@LIVE_JSON_BEGIN@@/END` 包裹 JSON。
`relay_probe.template.py` 属 v1 遗留（Mac 中转），v2 不再使用。

## 9. 告警规则（正常为空数组）

- SG `crypto-futures` 失败 / `futures_fresh=false` → warn，text 含 5m 级衍生数据最大滞后（排除 funding 8h）；
- SG `data_lag_s > 120` → warn（该字段天然含当前 1m bar 年龄 0~75s）；
- SG `htf_lag_s["15m"] > 1200` → warn（15m 收盘 + 5m 聚合 timer 天然上限约 1200s）；
- SG `/health` 无响应 / bars COUNT 超时 → warn；
- SG claim 索引条数 < Mac BOARD total → warn `SG claim 索引 39/41 · 差 2 条未同步`（真实同步滞后，需在 Mac/Mac 侧刷新索引）；
- HK 最新备份 >60min → warn；
- SG / HK / Mac 不可达 → `level=bad` 并降级对应节点。

## 10. 日志与自测

- `live/collector.log`：主日志，UTF-8 追加；>1MB 轮转为 `collector.log.1`。每轮记录 probe 状态/耗时、关键采样、
  `run ok=... took_ms=... nodes=[...] agents=[...] activity=... alerts=... errors=...`、tokens 汇总、每条 error/alert。
- `live/collector.stderr.log`：计划任务包装下的 stderr（崩溃 traceback）。
- `live/collector.stdout.log` / `server.stdout.log`：早期手工启动遗留（当前任务 stdout 已丢 NUL）。
- 契约自测：`python live/validate_live.py` → `PASS`（schema/字段/顺序/长度/12 agents/12-16 activity/tokens 非 0/bars 等逐项校验）。
  现场（2026-10-21 14:26）连跑 2 次 PASS，`took_ms` 4.0~4.3s，`nodes=win:ok mac:warn sg:ok hk:ok`，
  `claims 41/verified 0`，`tokens total 779.5M`，`bars 3628722/725743/241914/60479`，`u1 59/59`，`agents 12 条`，`activity 16 条`。

## 11. 排障

1. `live.json` 停更但任务 Running：检查 python 子进程是否残留/是否被 stdout 阻塞（见 §2），`collector.log` 尾部应有每轮 `run ok=`。
2. 四节点全 down 而手工跑正常：多为任务以无 console 方式起 ssh.exe 导致挂起 —— 本任务用 InteractiveToken + cmd 包装规避；
   仍异常时用 `Start-ScheduledTask` 在登录会话下重启。
3. SG `SSH 超时`：先手工 `ssh -i <sg_key> -T root@<sg_host> "hostname"` 测握手（正常 3~8s）；偶发慢可调 `local.json` 的 `sg_timeout`。
4. SG/HK `SSH 连接失败`：先查 `known_hosts` 主机键（§1），再查私钥 ACL。
5. `tokens` 为 0：确认 DSH 会话缓存目录存在、cwd 过滤值正确（Win: `C:\keshihua`/`C:\dsh`；Mac: `/Users/sen/look`），`errors` 会记录解析失败数。
6. 8123 打不开：`Get-NetTCPConnection -LocalPort 8123 -State Listen` 看是否 `0.0.0.0` + 任务 STATE Running；
   页面 fetch 相对路径 `live.json`，服务根目录必须是 `C:\dsh\agent-display`。

## 12. 依赖与边界

- Windows Python 3.12（现场 `C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe`），仅标准库；
  Windows OpenSSH 客户端（`shutil.which("ssh")`）。
- Mac 侧有 `python3`；SG/HK 侧有 `python3` + `sqlite3`（标准库）。
- 只读：不改远端服务/配置/文件；不碰 DSH 本体与其它项目计划任务；不 git commit/push。
- v1→v2 变更：新增真实 tokens / metrics / 12 agents / 12-16 activity；SG/HK 改 Win 直连（SG 用常驻会话）；
  claims 补全 5 档；新增 `validate_live.py`；新增本 README 与计划任务。v1 的 `nodes/claims/progress/alerts` 结构与降级逻辑保留。
