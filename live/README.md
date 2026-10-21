# live/ — crypto-agent 跨机实况采集器（agent-live/1）

给「Agent 战术大屏」跨机实况数据条提供数据源：采集 **WIN / MAC / SG / HK** 四节点只读状态，
原子写出 `C:\dsh\agent-display\live.json`，页面每 15s fetch 一次。

- 本目录写作用域：`C:\dsh\agent-display\live\`；输出文件：`C:\dsh\agent-display\live.json`。
- 不改 `index.html`、不 git commit/push、**不创建计划任务/注册表启动项**（爸爸 2026-10-20 令）。
- 远端（Mac / SG / HK）**只读**：探针源码经 stdin 管道执行，不在远端落任何文件、不改远端配置。

## 1. 启动 / 停止

本机 Windows Python 3.12（只用标准库）：
`C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe`

```powershell
$py = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe'

# 采一次（默认 --once），约 4.5–5.5s，写 live.json
& $py C:\dsh\agent-display\live\collect_live.py

# 常驻循环：每 15s 一次（固定节拍，按采集开始时间对齐）
$env:PYTHONUTF8 = '1'
& $py C:\dsh\agent-display\live\collect_live.py --loop 15

# 后台常驻（隐藏窗口，PID 用 -PassThru 拿到）
$env:PYTHONUTF8 = '1'
$p = Start-Process -FilePath $py `
  -ArgumentList 'C:\dsh\agent-display\live\collect_live.py','--loop','15' `
  -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput 'C:\dsh\agent-display\live\collector.stdout.log' `
  -RedirectStandardError  'C:\dsh\agent-display\live\collector.stderr.log'
"collector PID = $($p.Id)"

# 停止
Stop-Process -Id <PID>            # 后台
# 前台直接 Ctrl+C（会写一行 "collector stopped: KeyboardInterrupt"）
# 查 PID：Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
#         Where-Object { $_.CommandLine -like '*collect_live.py*' } | Select ProcessId,CommandLine
```

`--loop SEC` 的含义是**采集开始时刻的最小间隔**：若单次采集耗时 5s、SEC=15，则下次在 15s 后开始，
不会漂成 20s；单次若超时严重则至少间隔 1s，避免打满。

## 2. 数据契约（`live.json`，schema = `agent-live/1`）

字段顺序固定；`nodes` 顺序固定 `win → mac → sg → hk`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema` | str | 固定 `agent-live/1` |
| `ts` | str | 本机本地时间 `YYYY-MM-DD HH:MM:SS`（Asia/Shanghai） |
| `epoch` | int | Unix 秒 |
| `collect.ok` | bool | 本次采集无错误（`errors` 为空）才为 true |
| `collect.took_ms` | int | 本次采集总耗时（毫秒） |
| `collect.errors` | str[] | 每源失败原因（`mac: ...` / `sg: ...` / ...），正常为空数组 |
| `nodes[].id/label/role` | str | 固定：`win/WIN/研究`、`mac/MAC/开发`、`sg/SG/采集`、`hk/HK/备份` |
| `nodes[].state` | str | `ok` \| `warn` \| `down` \| `unknown` |
| `nodes[].f1/f2` | str | 短字符串，各 ≤24 字符，超长截断加 `…` |
| `claims.total/verified` | int \| null | 来自 Mac `BOARD.md` 的 claim 分布表（total=各档求和，verified=`verified` 行）；Mac 不可达时 null |
| `progress.u1` | str | `59/59 @13:05`（Mac `verify_report.json` 的 matched/checked @ 文件 mtime）；未知 `—` |
| `progress.commit/commit_at` | str | Mac `~/crypto-agent` 的 git HEAD 短哈希 / 本地 HH:MM；未知空串 |
| `alerts[]` | `{level,text}[]` | `level` ∈ `bad` \| `warn` \| `info`；可空数组 |

不可达降级（硬要求）：远端不可达时对应节点 `state=down`、`f1="不可达"`、`f2=""`，
`collect.ok=false` 且 `errors` 记原因，**仍然原子写出 live.json**。

体积格式统一 1024 进制（MiB）：`87M` / `870M` / `53G`；时间差格式：`13m` / `4.6h`。

## 3. 探针清单（全部只读）

| 探针 | 执行位置 / 方式 | 采集内容 |
|---|---|---|
| `collect_live.py::win_collect` | 本机进程内 | `C:\research` 的 raw/db/jobs/results 大小与文件数、`db\crypto.duckdb` 大小+mtime、`results\u1\*.json` 数量+最新 mtime、`venv\Scripts\python.exe -c "import duckdb"` 版本、`C:\crypto-agent` git HEAD |
| `probes/mac_probe.py` | `ssh -i ~/.ssh/xiaoma_mac user@<mac-host> "python3 -"`，stdin 送脚本 | `~/crypto-agent` git HEAD/commit epoch/dirty 数；`BOARD.md` claim 分布；`~/taolunchaijie/u1/verify_report.json` summary+mtime；`pgrep -f "DeepSeek Harness"` |
| `probes/relay_probe.template.py` | 同上，一次 Win→Mac SSH | Mac 中转：并发 `ssh eth-sg python3 -` 与 `ssh eth-hk python3 -`（内层显式接 stdin、不加 `-n`），单源 12s 超时 |
| `probes/sg_probe.py` | 由 Mac 中转，SG 上 `python3 -`，stdin 送脚本 | `systemctl list-units 'crypto-*' --plain --no-legend --no-pager`、`http://127.0.0.1:8710/health`（urllib，4s）、`df -k /`、`free -k` |
| `probes/hk_probe.py` | 由 Mac 中转，HK 上 `python3 -`，stdin 送脚本 | `du -sk /srv/crypto-agent`、`find ... -printf '%T@\n' \| sort -n \| tail -1` 最新备份 mtime、`df -k /` |

- `relay_probe.template.py` 是模板：采集器运行时把 `sg_probe.py`/`hk_probe.py` 源码用 JSON 字符串内嵌进模板，
  组装后整体经 stdin 送入 Mac；**改 SG/HK 探针不需要改模板**。
- 超时：Mac 直连探针 15s；SG/HK 内层各 12s；外层 Mac 中转 15s；所有远端探针 `subprocess.run(timeout=...)`。
- 实测：Mac 直连 ~0.3–1.3s；HK 中继 ~0.8–1.5s；SG 中继 ~4–5s（Mac→SG RTT 223ms，中转 SSH 握手是主要成本）。

## 4. 节点状态与告警规则

| 节点 | ok / warn / down 判定 |
|---|---|
| win | 采集器在跑即 `ok`；本地数据目录不可读等异常 `warn` 并记 errors |
| mac | 可达且读到 git HEAD → `ok`；git 读失败或工作区 dirty → `warn`；SSH 不可达 → `down`；探针异常 → `unknown` |
| sg | `crypto-futures` failed 或 `futures_fresh=false`、`data_lag_s>120`、`htf_lag_s["15m"]>1200`、`/health` 不可达 → `warn`；SSH 不可达 → `down`；探针异常 → `unknown` |
| hk | 最新备份文件 mtime 距今 >60min → `warn`；不可达 → `down`；探针异常 → `unknown` |

告警规则（其余正常不产生告警，`alerts` 可为空）：
- SG `crypto-futures` 失败 / `futures_fresh=false` → `warn`，text 含衍生数据滞后时长（`futures_lag_s` 中 5m 级序列最大值，排除 funding 8h 节奏）；
- SG `data_lag_s > 120` → `warn`（text 精确到 0.1s；阈值 2026-10-21 14:15 由 60 修正：该字段天然含当前 1m bar 年龄 0–75s）；
- SG `htf_lag_s["15m"] > 1200` → `warn`（阈值由 900 修正：15m 收盘 + 5m 聚合 timer 天然上限约 1200s）；
- SG `/health` 端点无响应 → `warn`（节点可达但健康检查失败）；
- HK 最新备份 >60min → `warn`；
- Mac 不可达 → `level=bad`（**跨机数据全断，含 SG/HK 中转**）。
- HK 无 `crypto-*` systemd unit（备份由 SG push），不采集 unit，不误报。

## 5. 故障降级行为

- **单源失败不阻塞**：三路（Win 本地 / Mac 直连 / Mac 中转）并行，各自 try/except + 超时；
  某一源超时/异常时其它源照常出数，仍写出完整 `live.json`。
- Mac 不可达时 SG/HK 也随中转而 `down`；此时 `claims=null`、`progress.u1="—"`、`commit=""`。
- `collect.ok` = `errors` 为空；页面可按 `collect.ok` / `nodes[].state` / `alerts` 分级展示。
- **原子写**：先写同目录临时文件 `live/live.json.tmp`（flush+fsync），再 `os.replace()` 覆盖 `live.json`；
  页面任意时刻读取都不会拿到半截 JSON。编码 UTF-8 **无 BOM**。
- 写 live.json 的异常（磁盘满/权限）会在日志中留痕；`--loop` 模式下单轮崩溃不会退出循环。

## 6. 日志

`live/collector.log`：追加写，UTF-8；超过 1MB 轮转为 `collector.log.1`（覆盖旧 `.1`）。
每轮记录：`probe <源> <ok|down|error> <耗时>s`、`probe win ...`、各源关键采样值、
`run ok=... took_ms=... nodes=[...] alerts=... errors=...`，以及每条 error/alert 的明细。
后台启动方式另产生 `collector.stdout.log` / `collector.stderr.log`（可选）。

## 7. 自测 / 校验

```powershell
$py = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe'
$env:PYTHONUTF8 = '1'
& $py C:\dsh\agent-display\live\collect_live.py
& $py -c "import json; d=json.load(open(r'C:\dsh\agent-display\live.json',encoding='utf-8')); print(d['schema'], d['ts'], [n['id']+':'+n['state'] for n in d['nodes']], d['collect']['ok'], d['collect']['took_ms'])"
```

正常现场（2026-10-21 13:19 实测）：单次 4.6–6.0s，`live.json` ≈1.0–1.1KB，节点
`win:ok mac:ok sg:ok hk:ok`，claims 41/0，u1 59/59。
降级实测（伪 Mac 地址）：6.0s 写完，`mac/sg/hk down`、`collect.ok=false`、3 条 errors、1 条 bad 告警，契约校验通过。

## 8. 依赖与边界

- Windows Python ≥3.9（现场 3.12.10），仅标准库；Windows OpenSSH 客户端（`C:\Windows\System32\OpenSSH\ssh.exe`）。
- Mac：`user@<mac-host>`，key `~/.ssh/xiaoma_mac`，有 `python3`，
  `~/.ssh/config` 已配 `eth-sg` / `eth-hk` 别名（Mac 归军师，只读复用）。
- Mac→SG 当前 RTT ≈223ms，故 SG 中继单次约 4–5s 属正常；不要为此调大超时。
- 不重启/不改 Lead 的静态服务 `127.0.0.1:8899`；不碰 `index.html`/`README.md`/`CHANGELOG.md`。

## 9. 排障

1. 看 `collector.log` 尾部 5–10 行（probe 状态与 errors）。
2. 手工验证链路：
   `ssh -i ~/.ssh/xiaoma_mac -T user@<mac-host> "hostname"`；
   `ssh ... user@<mac-host> "ssh -o BatchMode=yes -o ConnectTimeout=6 -T eth-sg hostname"`。
3. `python3 -V` 各端 ≥3.6；Python 2 会直接让探针失败（日志 `远端退出码`/`无法解析`）。
4. 页面拿到数据但字段为空：确认 `live.json` 是 `ts` 最新的那份，且 `collect.ok`/`errors` 说明原因。
