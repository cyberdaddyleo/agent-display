#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crypto-agent 跨机实况采集器 v2（只读）——「Agent 战术大屏」数据源。

契约：agent-live/2（在 v1 的 nodes/claims/progress/alerts 基础上新增 tokens/metrics/agents/activity）。

用法（本机 python: C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python312\\python.exe）：
    python live/collect_live.py              # 采集一次，写 C:\\dsh\\agent-display\\live.json
    python live/collect_live.py --loop 15    # 每 15s 循环采集（页面 15s fetch 一次）

架构（v2）：
- Win 直连三路 SSH（不再经 Mac 中转 relay）：
    Mac  user@<mac-host>             key ~/.ssh/xiaoma_mac        timeout 15s
    SG   root@<sg-host>              key .../sg.pem               timeout 12s
    HK   root@<hk-host>              key .../sui.pem              timeout 12s
  每路独立 subprocess 超时 + try/except，单路失败只降级该节点。
- 远端探针经 ssh "python3 -" 从 stdin 管道执行，不在远端落任何文件。
- 真实 token：Win/Mac 各自读 ~/.dsh/storages/session_projcache/sessions/*.json，
  按 cwd 过滤本项目后累加 tokenUsage/sessionStats；解析失败降级为 0 + errors。
- 只读采集：Win 本地目录/git；SG systemctl/health/journal/SQLite COUNT；HK du/find/df。
- 原子写 live.json（live/ 内临时文件 + os.replace），UTF-8 无 BOM。
- 日志 live/collector.log 追加，>1MB 轮转为 collector.log.1。
- 只允许标准库。
"""
import argparse
import base64
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DISPLAY_DIR = BASE_DIR.parent
OUT_PATH = DISPLAY_DIR / "live.json"
TMP_PATH = BASE_DIR / "live.json.tmp"
LOG_PATH = BASE_DIR / "collector.log"
PROBE_DIR = BASE_DIR / "probes"

SSH = shutil.which("ssh") or r"C:\Windows\System32\OpenSSH\ssh.exe"
SSH_OPTS = [
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=6",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "IdentitiesOnly=yes",
    "-T",
]

# ---------------------------------------------------------------------------
# 部署配置：真实主机 / 密钥路径放 live/local.json（已 gitignore，不入公开仓库）。
# 缺省为占位值，公开仓库不泄露内网与服务器地址；字段示例见 live/README.md。
# ---------------------------------------------------------------------------
def _load_local_cfg():
    try:
        return json.loads((BASE_DIR / "local.json").read_text(encoding="utf-8"))
    except Exception:
        return {}

_LOCAL = _load_local_cfg()
def _cfg(key, default):
    v = _LOCAL.get(key)
    return v if v not in (None, "") else default

MAC_KEY = Path(_cfg("mac_key", str(Path.home() / ".ssh" / "xiaoma_mac")))
MAC_HOST = _cfg("mac_host", "user@mac-host")
MAC_TIMEOUT = int(_cfg("mac_timeout", 15))

SG_KEY = Path(_cfg("sg_key", str(Path.home() / ".ssh" / "sg.pem")))
SG_HOST = _cfg("sg_host", "root@sg-host")
SG_TIMEOUT = int(_cfg("sg_timeout", 22))  # Win->SG 握手 4-5s + probe 5-6s，12s 会偶发超时

HK_KEY = Path(_cfg("hk_key", str(Path.home() / ".ssh" / "sui.pem")))
HK_HOST = _cfg("hk_host", "root@hk-host")
HK_TIMEOUT = int(_cfg("hk_timeout", 12))

WIN_GIT = Path(r"C:\Users\Administrator\AppData\Local\hermes\tools\git-2.53.0+3-win32-x64\cmd\git.exe")
RESEARCH = Path(r"C:\research")
WIN_REPO = Path(r"C:\crypto-agent")
WIN_VENV_PY = RESEARCH / "venv" / "Scripts" / "python.exe"
WIN_TOKEN_DIR = Path.home() / ".dsh" / "storages" / "session_projcache" / "sessions"
WIN_TOKEN_CWDS = ("C:\\keshihua", "C:\\dsh")

LOG_MAX_BYTES = 1024 * 1024

BEGIN = "@@LIVE_JSON_BEGIN@@"
END = "@@LIVE_JSON_END@@"

TOKEN_ZERO = {
    "sessions": 0,
    "inputTokens": 0,
    "outputTokens": 0,
    "cacheReadTokens": 0,
    "cacheWriteTokens": 0,
    "turns": 0,
    "steps": 0,
    "decodeTokens": 0,
    "llmMs": 0,
}

AGENT_SPEC = [
    ("collector", "COLLECTOR", "采集器", "SG"),
    ("aggregate", "AGGREGATE", "聚合", "SG"),
    ("futures", "FUTURES", "衍生采集", "SG"),
    ("agent-svc", "AGENT-SVC", "分析服务", "SG"),
    ("claims", "CLAIMS", "claim 库", "MAC"),
    ("retrieval", "RETRIEVAL", "检索层", "MAC"),
    ("replay", "REPLAY", "回放引擎", "MAC"),
    ("u1-vision", "U1-VISION", "历史下载", "MAC"),
    ("u1-verify", "U1-VERIFY", "数据校验", "MAC"),
    ("duckdb", "DUCKDB", "研究库", "WIN"),
    ("backup", "BACKUP", "备份", "HK"),
    ("research", "RESEARCH", "研究节点", "WIN"),
]


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def utf8_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def log(message):
    line = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + message
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_MAX_BYTES:
            os.replace(str(LOG_PATH), str(LOG_PATH.with_name("collector.log.1")))
        with open(LOG_PATH, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    try:
        print(line)
    except (OSError, ValueError):
        pass


def short(text, limit=200):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def trunc(text, limit=24):
    text = "" if text is None else str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def fmt_size_mib(nbytes):
    """字节数 -> 人类可读（MiB/GiB，1024 进制）。"""
    if nbytes is None:
        return "?"
    mib = float(nbytes) / 1048576.0
    if mib >= 1024:
        return "%.1fG" % (mib / 1024.0)
    if mib >= 10:
        return "%.0fM" % mib
    if mib >= 1:
        return "%.1fM" % mib
    return "%.0fK" % (float(nbytes) / 1024.0)


def fmt_gib(nbytes):
    if nbytes is None:
        return "?"
    return "%.1fG" % (float(nbytes) / 1073741824.0)


def fmt_disk_g(avail_kb):
    """df -k 的 1K 块 -> 整数 GiB。"""
    if avail_kb is None:
        return "?"
    return "%.0fG" % (float(avail_kb) / 1048576.0)


def fmt_mem_g(avail_kb):
    if avail_kb is None:
        return "?"
    return "%.1fG" % (float(avail_kb) / 1048576.0)


def fmt_count(n):
    """整数 -> 面板短计数（3.6M / 726K / 60K）。"""
    if n is None:
        return "?"
    n = int(n)
    if n >= 1000000:
        return "%.1fM" % (n / 1000000.0) if n < 10000000 else "%.0fM" % (n / 1000000.0)
    if n >= 1000:
        return "%.0fK" % (n / 1000.0)
    return str(n)


def fmt_age(seconds):
    """时间差（秒）-> 简短文本，如 13m / 4.6h / 2.2d。"""
    if seconds is None:
        return "?"
    seconds = float(seconds)
    if seconds < 60:
        return "%.0fs" % seconds
    if seconds < 3600:
        return "%.0fm" % (seconds / 60.0)
    if seconds < 86400:
        return "%.1fh" % (seconds / 3600.0)
    return "%.1fd" % (seconds / 86400.0)


def fmt_lag(seconds):
    """滞后秒数 -> 简短文本（<120s 保留 1 位小数）。"""
    if seconds is None:
        return "?"
    seconds = float(seconds)
    if seconds < 120:
        return "%.1fs" % seconds
    if seconds < 3600:
        return "%.0fm" % (seconds / 60.0)
    return "%.1fh" % (seconds / 3600.0)


def local_hhmm(epoch):
    if not epoch:
        return "--:--"
    try:
        return datetime.fromtimestamp(float(epoch)).strftime("%H:%M")
    except (OSError, OverflowError, ValueError):
        return "--:--"


def fmt_tokens(n):
    """token 数 -> 面板短文本（1.2k / 8.3M）。"""
    if n is None:
        return "?"
    n = int(n)
    if n >= 1000000:
        return "%.1fM" % (n / 1000000.0)
    if n >= 1000:
        return "%.1fk" % (n / 1000.0)
    return str(n)


def clean_board_text(text):
    text = re.sub(r"[`*_#>|]", " ", str(text or ""))
    text = text.replace("✅", " ").replace("🔴", " ").replace("🟠", " ").replace("🟢", " ")
    return " ".join(text.split())


def board_note(rows, limit=24):
    """BOARD 行文本 -> agent note（取首句并截断）。"""
    if not rows:
        return ""
    chosen = None
    for row in rows:
        if "✅" in row:
            chosen = row
            break
    if chosen is None:
        chosen = max(rows, key=len)
    text = clean_board_text(chosen)
    for sep in ("，", ",", "；", ";", "。"):
        if sep in text:
            text = text.split(sep, 1)[0]
            break
    return trunc(" ".join(text.split()), limit)


def make_node(nid, label, role, state, f1, f2):
    if state not in ("ok", "warn", "down", "unknown"):
        state = "unknown"
    return {
        "id": nid,
        "label": label,
        "role": role,
        "state": state,
        "f1": trunc(f1),
        "f2": trunc(f2),
    }


def make_agent(aid, label, zh, where, state, pct, note):
    if state not in ("ok", "warn", "down", "unknown"):
        state = "unknown"
    try:
        pct = max(0, min(100, int(round(pct))))
    except (TypeError, ValueError):
        pct = 0
    return {
        "id": aid,
        "label": label,
        "zh": zh,
        "where": where,
        "state": state,
        "pct": pct,
        "note": trunc(note, 24),
    }


def clamp_pct(value, floor=40):
    try:
        return max(floor, min(100, int(round(value))))
    except (TypeError, ValueError):
        return floor


# ---------------------------------------------------------------------------
# 远端探针执行
# ---------------------------------------------------------------------------

def extract_payload(stdout_text):
    start = stdout_text.find(BEGIN)
    end = stdout_text.find(END)
    if start < 0 or end < 0 or end <= start:
        return None
    chunk = stdout_text[start + len(BEGIN):end].strip()
    try:
        return json.loads(chunk)
    except ValueError:
        return None


def ssh_command(key_path, host):
    return [SSH] + SSH_OPTS + ["-i", str(key_path), host, "python3", "-"]


def run_probe(label, probe_name, key_path, host, timeout):
    """通过 ssh stdin 管道执行远端探针，返回 {status: ok|down|error, payload/error, secs}。"""
    started = time.time()
    try:
        script = (PROBE_DIR / probe_name).read_bytes()
    except OSError as exc:
        return {"status": "error", "error": "读取探针失败 %s: %s" % (label, exc), "secs": 0.0}

    try:
        proc = subprocess.run(
            ssh_command(key_path, host),
            input=script,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"status": "down", "error": "SSH 超时 %ss" % timeout, "secs": round(time.time() - started, 2)}
    except OSError as exc:
        return {"status": "error", "error": "启动 ssh 失败: %s" % exc, "secs": round(time.time() - started, 2)}

    secs = round(time.time() - started, 2)
    stdout_text = proc.stdout.decode("utf-8", "replace")
    stderr_text = proc.stderr.decode("utf-8", "replace").strip()
    payload = extract_payload(stdout_text)

    if payload is not None and isinstance(payload, dict) and payload.get("probe_error"):
        return {"status": "error", "error": "远端探针异常: %s" % short(payload["probe_error"]), "secs": secs}
    if proc.returncode != 0:
        if proc.returncode == 255:
            return {"status": "down", "error": "SSH 连接失败: %s" % short(stderr_text or "rc=255"), "secs": secs}
        return {"status": "error", "error": "远端退出码 %s: %s" % (proc.returncode, short(stderr_text or stdout_text)), "secs": secs}
    if payload is None:
        return {"status": "error", "error": "探针输出无法解析: %s" % short(stderr_text or stdout_text), "secs": secs}
    if not isinstance(payload, dict):
        return {"status": "error", "error": "探针输出不是 JSON 对象", "secs": secs}
    return {"status": "ok", "payload": payload, "secs": secs}


def run_probe_safe(label, probe_name, key_path, host, timeout):
    try:
        return run_probe(label, probe_name, key_path, host, timeout)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": "采集线程异常: %s" % short(exc), "secs": 0.0}


# ---------------------------------------------------------------------------
# SG 常驻 SSH 会话（规避 Win->SG 每次握手 3-8s 的固定开销）
# ---------------------------------------------------------------------------
# 实测：Win->SG 单次 SSH 握手 3-8s（同一网络下 Mac->SG 也要 2.7-3.8s，属 SG 侧
# sshd/链路固定成本），若每 15s 都重连，探针总耗时会在 6.5-12s 间抖动甚至超时。
# 做法：常驻一条 ssh "python3 -u -c <守护进程>" 会话，逐轮把探针源码（base64）经
# stdin 送入远端内存执行；仍然是 Win 直连 SG，不落任何远端文件；单轮 12s 超时不变。
# 会话断开/超时 -> 下一轮自动重建（首轮约 8s，之后约 3-4s）。

REMOTE_PROBE_DAEMON = r'''
import sys, json, base64
IDLE = 120
def emit(payload):
    sys.stdout.write("@@LIVE_JSON_BEGIN@@\n")
    sys.stdout.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n")
    sys.stdout.write("@@LIVE_JSON_END@@\n")
    sys.stdout.flush()
while True:
    try:
        import select
        r, _, _ = select.select([sys.stdin], [], [], IDLE)
        if not r:
            break
        line = sys.stdin.readline()
    except Exception:
        break
    if not line:
        break
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except Exception:
        continue
    op = req.get("op")
    if op == "exit":
        break
    if op != "probe":
        continue
    try:
        src = base64.b64decode(req.get("src") or "").decode("utf-8")
        ns = {"__name__": "__main__", "__file__": "<remote-probe>"}
        exec(compile(src, "<remote-probe>", "exec"), ns)
    except Exception as exc:
        emit({"probe_error": type(exc).__name__ + ": " + str(exc)[:300]})
'''


class PersistentProbe:
    """常驻 ssh 探针会话：spawn 时付一次握手成本，之后每轮只传探针源码。"""

    def __init__(self, name, key_path, host):
        self.name = name
        self.key_path = key_path
        self.host = host
        self.proc = None
        self.lines = queue.Queue()
        self.stderr_tail = []
        self._spawn_failures = 0

    def _spawn(self):
        remote_cmd = 'python3 -u -c "import base64;exec(base64.b64decode(\'%s\').decode(\'utf-8\'))"' % (
            base64.b64encode(REMOTE_PROBE_DAEMON.encode("utf-8")).decode("ascii"),
        )
        cmd = [SSH] + SSH_OPTS + ["-i", str(self.key_path), self.host, remote_cmd]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0,
        )
        self.lines = queue.Queue()
        self.stderr_tail = []
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()

    def _pump_stdout(self):
        try:
            for line in iter(self.proc.stdout.readline, b""):
                self.lines.put(line)
        except (OSError, ValueError):
            pass
        self.lines.put(None)

    def _pump_stderr(self):
        try:
            for line in iter(self.proc.stderr.readline, b""):
                text = line.decode("utf-8", "replace").strip()
                if text:
                    self.stderr_tail.append(text[:200])
                    if len(self.stderr_tail) > 20:
                        del self.stderr_tail[:10]
        except (OSError, ValueError):
            pass

    def _reset(self):
        proc = self.proc
        self.proc = None
        if proc is None:
            return
        try:
            proc.kill()
        except OSError:
            pass

    def close(self):
        proc = self.proc
        self.proc = None
        if proc is None:
            return
        try:
            proc.stdin.write(b'{"op":"exit"}\n')
            proc.stdin.flush()
        except (OSError, ValueError):
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass

    def _read_payload(self, timeout):
        buf = b""
        deadline = time.time() + timeout
        while True:
            remain = deadline - time.time()
            if remain <= 0:
                return None
            try:
                line = self.lines.get(timeout=remain)
            except queue.Empty:
                return None
            if line is None:
                return None
            buf += line
            text = buf.decode("utf-8", "replace")
            if END in text and BEGIN in text:
                return extract_payload(text)

    def probe(self, probe_name, timeout):
        started = time.time()
        try:
            script = (PROBE_DIR / probe_name).read_bytes()
        except OSError as exc:
            return {"status": "error", "error": "读取探针失败 %s: %s" % (self.name, exc), "secs": 0.0}
        if self.proc is None or self.proc.poll() is not None:
            try:
                self._spawn()
            except OSError as exc:
                self._spawn_failures += 1
                return {"status": "error", "error": "启动 ssh 会话失败: %s" % exc,
                        "secs": round(time.time() - started, 2)}
        # 清掉可能残留的输出
        while True:
            try:
                self.lines.get_nowait()
            except queue.Empty:
                break
        request = (json.dumps({"op": "probe", "src": base64.b64encode(script).decode("ascii")}) + "\n").encode("utf-8")
        try:
            self.proc.stdin.write(request)
            self.proc.stdin.flush()
        except (OSError, ValueError) as exc:
            self._reset()
            return {"status": "down", "error": "SG 会话写入失败: %s" % short(exc),
                    "secs": round(time.time() - started, 2)}
        payload = self._read_payload(timeout)
        if payload is None:
            self._reset()
            self._spawn_failures += 1
            return {"status": "down", "error": "SG 常驻会话超时 %ss" % timeout,
                    "secs": round(time.time() - started, 2)}
        secs = round(time.time() - started, 2)
        if isinstance(payload, dict) and payload.get("probe_error"):
            return {"status": "error", "error": "远端探针异常: %s" % short(payload["probe_error"]), "secs": secs}
        if not isinstance(payload, dict):
            return {"status": "error", "error": "探针输出不是 JSON 对象", "secs": secs}
        return {"status": "ok", "payload": payload, "secs": secs}


_SG_SESSION = None


def run_sg_probe():
    global _SG_SESSION
    try:
        if _SG_SESSION is None:
            _SG_SESSION = PersistentProbe("sg", SG_KEY, SG_HOST)
        return _SG_SESSION.probe("sg_probe.py", SG_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": "SG 常驻会话异常: %s" % short(exc), "secs": 0.0}


def close_sg_probe():
    global _SG_SESSION
    if _SG_SESSION is not None:
        try:
            _SG_SESSION.close()
        finally:
            _SG_SESSION = None


# ---------------------------------------------------------------------------
# Win 本地只读采集
# ---------------------------------------------------------------------------

def dir_stats(path):
    total = 0
    files = 0
    try:
        for root, _dirs, names in os.walk(path):
            for name in names:
                try:
                    total += os.stat(os.path.join(root, name)).st_size
                    files += 1
                except OSError:
                    continue
    except OSError:
        return None, None
    return total, files


def mtime_int(path):
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return None


def run_local(args, timeout=10):
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return proc.returncode, proc.stdout.decode("utf-8", "replace").strip(), proc.stderr.decode("utf-8", "replace").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", "%s: %s" % (type(exc).__name__, exc)


def read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def collect_tokens_win(token_dir=WIN_TOKEN_DIR, cwds=WIN_TOKEN_CWDS):
    """累加 Win 本地 cwd ∈ cwds 的 session token / stats 用量。"""
    totals = dict(TOKEN_ZERO)
    errors = 0
    try:
        files = list(token_dir.glob("*.json"))
    except OSError:
        return totals, 1
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            errors += 1
            continue
        rec = doc.get("record") or {}
        if (rec.get("identity") or {}).get("cwd") not in cwds:
            continue
        rows = rec.get("rows") or {}
        tu = ((rows.get("tokenUsage") or {}).get("val") or {}).get("totals") or {}
        ss = (rows.get("sessionStats") or {}).get("val") or {}
        totals["sessions"] += 1
        for key, val in (
            ("inputTokens", tu.get("uncachedInputTokens")),
            ("outputTokens", tu.get("outputTokens")),
            ("cacheReadTokens", tu.get("cacheReadTokens")),
            ("cacheWriteTokens", tu.get("cacheWriteTokens")),
            ("turns", ss.get("turns")),
            ("steps", ss.get("steps")),
            ("decodeTokens", ss.get("decodeTokens")),
            ("llmMs", ss.get("llmMs")),
        ):
            try:
                totals[key] += int(val or 0)
            except (TypeError, ValueError):
                pass
    return totals, errors


def win_collect():
    data = {"warnings": [], "now": int(time.time())}

    raw_bytes, raw_files = dir_stats(RESEARCH / "raw")
    data["raw"] = {"bytes": raw_bytes, "files": raw_files, "mtime": mtime_int(RESEARCH / "raw")}
    if raw_bytes is None:
        data["warnings"].append("raw 目录不可读")

    fapi_bytes, fapi_files = dir_stats(RESEARCH / "fapi")
    data["fapi"] = {"bytes": fapi_bytes, "files": fapi_files, "mtime": mtime_int(RESEARCH / "fapi")}
    if fapi_bytes is None:
        data["warnings"].append("fapi 目录不可读")

    u1_dir = RESEARCH / "results" / "u1"
    u1_files = []
    try:
        for p in sorted(u1_dir.iterdir()):
            if p.is_file():
                u1_files.append({"name": p.name, "size": p.stat().st_size, "mtime": int(p.stat().st_mtime)})
    except OSError:
        data["warnings"].append("results/u1 不可读")
    data["u1_files"] = u1_files
    data["u1_files_by_name"] = {item["name"]: item for item in u1_files}

    duckdb = RESEARCH / "db" / "crypto.duckdb"
    data["duckdb"] = {"bytes": None, "mtime": None}
    try:
        st = duckdb.stat()
        data["duckdb"] = {"bytes": st.st_size, "mtime": int(st.st_mtime)}
    except OSError:
        data["warnings"].append("crypto.duckdb 不可读")

    fv = read_json_file(u1_dir / "full_verify.json")
    data["full_verify"] = {}
    if isinstance(fv, dict):
        data["full_verify"] = {
            "klines": fv.get("klines"),
            "klines_symbols": fv.get("klines_symbols"),
            "funding": fv.get("funding"),
            "oi": fv.get("oi"),
            "taker": fv.get("taker"),
            "db_bytes": fv.get("db_bytes"),
            "mtime": data["u1_files_by_name"].get("full_verify.json", {}).get("mtime"),
        }
    aux = read_json_file(u1_dir / "aux_load.json")
    data["aux_load"] = aux if isinstance(aux, dict) else {}
    if data["aux_load"]:
        data["aux_mtime"] = data["u1_files_by_name"].get("aux_load.json", {}).get("mtime")
    bmf = read_json_file(u1_dir / "build_manifest_full.json")
    data["build_manifest_full"] = {}
    if isinstance(bmf, dict):
        data["build_manifest_full"] = {
            "generated_at": bmf.get("generated_at"),
            "pairs_count": bmf.get("pairs_count"),
            "elapsed_s": bmf.get("elapsed_s"),
            "mtime": data["u1_files_by_name"].get("build_manifest_full.json", {}).get("mtime"),
        }

    git = {"head": None, "log": [], "dirty": None}
    git_exe = str(WIN_GIT) if WIN_GIT.exists() else (shutil.which("git") or "")
    if git_exe and (WIN_REPO / ".git").exists():
        rc, out, _err = run_local([git_exe, "-C", str(WIN_REPO), "rev-parse", "--short", "HEAD"], timeout=8)
        if rc == 0 and out:
            git["head"] = out.splitlines()[0]
        rc, out, _err = run_local([git_exe, "-C", str(WIN_REPO), "log", "-3", "--format=%h|%ct|%s"], timeout=8)
        if rc == 0 and out:
            for line in out.splitlines():
                parts = line.split("|", 2)
                if len(parts) != 3:
                    continue
                try:
                    ct = int(parts[1])
                except ValueError:
                    continue
                git["log"].append({"h": parts[0], "ct": ct, "subject": parts[2][:120]})
        rc, out, _err = run_local([git_exe, "-C", str(WIN_REPO), "status", "--porcelain"], timeout=8)
        if rc == 0:
            git["dirty"] = len([ln for ln in out.splitlines() if ln.strip()])
    else:
        data["warnings"].append("Win git 仓库不可用")
    data["git"] = git

    tokens, token_errors = collect_tokens_win()
    data["tokens"] = tokens
    data["token_errors"] = token_errors
    return data


# ---------------------------------------------------------------------------
# 派生逻辑：节点 / claims / 指标 / agents / activity
# ---------------------------------------------------------------------------

def futures_lag_rep(health):
    """futures_lag_s 里挑「5m 级」系列（排除 funding 8h 节奏）的最大滞后秒数。"""
    if not isinstance(health, dict):
        return None
    lags = health.get("futures_lag_s")
    if not isinstance(lags, dict):
        return None
    values = [(str(k), v) for k, v in lags.items() if isinstance(v, (int, float))]
    if not values:
        return None
    five_min = [v for k, v in values if "funding" not in k.lower()]
    return max(five_min) if five_min else max(v for _k, v in values)


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_sg_ctx(r_sg):
    ctx = {
        "ok": r_sg["status"] == "ok",
        "health": None,
        "lag": None,
        "htf15": None,
        "futures_fresh": None,
        "data_fresh": None,
        "futures_lags": {},
        "futures_bad": None,
        "units_ok": None,
        "units_total": None,
        "bars": {"m1": None, "m5": None, "m15": None, "h1": None, "latest": {}},
        "disk_kb": None,
        "mem_kb": None,
        "timers": {},
        "claim_index": {"total": None, "status": {}},
        "collector_log_ts": None,
        "futures_log_ts": None,
        "db_bytes": None,
        "host": None,
        "now": None,
    }
    if not ctx["ok"]:
        return ctx
    payload = r_sg["payload"]
    ctx["host"] = payload.get("host")
    ctx["now"] = payload.get("now")
    health = payload.get("health")
    if isinstance(health, dict):
        ctx["health"] = health
        ctx["lag"] = safe_float(health.get("data_lag_s"))
        htf = health.get("htf_lag_s")
        if isinstance(htf, dict):
            ctx["htf15"] = safe_float(htf.get("15m"))
        ctx["futures_fresh"] = health.get("futures_fresh")
        ctx["data_fresh"] = health.get("data_fresh")
        if isinstance(health.get("futures_lag_s"), dict):
            ctx["futures_lags"] = health["futures_lag_s"]
    ctx["futures_bad"] = bool(payload.get("crypto_futures_failed")) or ctx["futures_fresh"] is False
    ctx["units_ok"] = payload.get("units_ok")
    ctx["units_total"] = payload.get("units_total")
    bars = payload.get("bars")
    if isinstance(bars, dict):
        ctx["bars"] = bars
    ctx["disk_kb"] = payload.get("disk_avail_kb")
    ctx["mem_kb"] = payload.get("mem_avail_kb")
    timers = payload.get("timers")
    if isinstance(timers, dict):
        ctx["timers"] = timers
    claims = payload.get("claim_index")
    if isinstance(claims, dict):
        ctx["claim_index"] = claims
    ctx["collector_log_ts"] = payload.get("collector_log_ts")
    ctx["futures_log_ts"] = payload.get("futures_log_ts")
    ctx["db_bytes"] = payload.get("db_bytes")
    return ctx


def build_mac_ctx(r_mac):
    ctx = {
        "ok": r_mac["status"] == "ok",
        "host": None, "now": None,
        "git": {}, "claims": None, "board_tasks": {}, "board_mtime": None,
        "u1": {}, "tokens": dict(TOKEN_ZERO), "token_errors": 0,
        "dsh": {"running": None, "count": 0},
    }
    if not ctx["ok"]:
        return ctx
    payload = r_mac["payload"]
    ctx["host"] = payload.get("host")
    ctx["now"] = payload.get("now")
    ctx["git"] = payload.get("git") or {}
    ctx["claims"] = payload.get("claims")
    ctx["board_tasks"] = payload.get("board_tasks") or {}
    ctx["board_mtime"] = payload.get("board_mtime")
    ctx["u1"] = payload.get("u1") or {}
    tokens = payload.get("tokens")
    if isinstance(tokens, dict):
        ctx["tokens"] = {key: tokens.get(key, 0) for key in TOKEN_ZERO}
    ctx["token_errors"] = payload.get("token_errors") or 0
    ctx["dsh"] = payload.get("dsh") or {"running": None, "count": 0}
    return ctx


def build_agents(mac, sg, hk, win, now):
    """12 条固定顺序 agents；state/pct/note 全部由真实数据推导。"""
    agents = []
    health = sg["health"] or {}
    requests = health.get("requests") if isinstance(health, dict) else None
    errors_n = health.get("errors") if isinstance(health, dict) else None

    # collector
    if not sg["ok"]:
        state, pct, note = "down", 0, "SG 不可达"
    else:
        if sg["data_fresh"] and sg["lag"] is not None and sg["lag"] <= 120:
            state, pct = "ok", 100
        else:
            state = "warn"
            pct = clamp_pct(100 - max(0.0, (sg["lag"] or 0) - 120) / 60.0 * 10)
        note = "15s 轮询 · lag %s" % fmt_lag(sg["lag"])
    agents.append(make_agent(*AGENT_SPEC[0], state, pct, note))

    # aggregate
    if not sg["ok"]:
        agents.append(make_agent(*AGENT_SPEC[1], "down", 0, "SG 不可达"))
    else:
        if sg["htf15"] is not None and sg["htf15"] <= 1200:
            state, pct = "ok", 100
        else:
            state = "warn"
            pct = clamp_pct(100 - max(0.0, (sg["htf15"] or 0) - 1200) / 300.0 * 10)
        agents.append(make_agent(*AGENT_SPEC[1], state, pct, "5m timer · HTF %s" % fmt_lag(sg["htf15"])))

    # futures
    if not sg["ok"]:
        agents.append(make_agent(*AGENT_SPEC[2], "down", 0, "SG 不可达"))
    else:
        lag_rep = futures_lag_rep(health)
        if sg["futures_bad"]:
            agents.append(make_agent(*AGENT_SPEC[2], "warn", clamp_pct(100 - (lag_rep or 0) / 600.0 * 10),
                                     "滞后 %s · 待修" % fmt_lag(lag_rep)))
        else:
            oi = safe_float(sg["futures_lags"].get("oi_5m"))
            taker = safe_float(sg["futures_lags"].get("taker_ratio_5m"))
            note = "OI %s · taker %s" % (fmt_lag(oi), fmt_lag(taker))
            agents.append(make_agent(*AGENT_SPEC[2], "ok", 100, note))

    # agent-svc
    if not sg["ok"]:
        agents.append(make_agent(*AGENT_SPEC[3], "down", 0, "SG 不可达"))
    else:
        healthy = bool(health) and errors_n == 0
        note = "8710 在线 · %s req" % (requests if requests is not None else "?")
        agents.append(make_agent(*AGENT_SPEC[3], "ok" if healthy else "warn", 100 if healthy else 70, note))

    # claims
    claims = mac["claims"]
    index = sg["claim_index"]
    if not mac["ok"] or not isinstance(claims, dict):
        agents.append(make_agent(*AGENT_SPEC[4], "unknown", 50, "数据未知"))
    else:
        total = claims.get("total")
        index_total = index.get("total") if isinstance(index, dict) else None
        if isinstance(total, int) and isinstance(index_total, int) and index_total < total:
            pct = clamp_pct(index_total / float(total) * 100, floor=0) if total else 0
            agents.append(make_agent(*AGENT_SPEC[4], "warn", pct, "%s 条 · 索引 %s" % (total, index_total)))
        else:
            agents.append(make_agent(*AGENT_SPEC[4], "ok", 100, "%s 条 · 索引 %s" % (total, index_total if index_total is not None else "?")))

    # retrieval / replay：来自 BOARD 任务行（真实状态文本）
    for idx, tid, fallback in ((5, "r0zCvK", "检索层"), (6, "r1xplE", "Replay 引擎")):
        rows = mac.get("board_tasks", {}).get(tid) or []
        if not mac["ok"]:
            agents.append(make_agent(*AGENT_SPEC[idx], "down", 0, "MAC 不可达"))
        elif rows:
            has_ok = any("✅" in row for row in rows)
            agents.append(make_agent(*AGENT_SPEC[idx], "ok" if has_ok else "warn", 100 if has_ok else 60, board_note(rows)))
        else:
            agents.append(make_agent(*AGENT_SPEC[idx], "unknown", 50, "BOARD 无记录"))

    # u1-vision
    u1 = mac["u1"] or {}
    symbols = u1.get("symbols")
    du_kb = u1.get("du_kb")
    if not mac["ok"]:
        agents.append(make_agent(*AGENT_SPEC[7], "down", 0, "MAC 不可达"))
    else:
        size_text = fmt_size_mib(du_kb * 1024) if du_kb is not None else "?"
        if symbols and symbols >= 500:
            agents.append(make_agent(*AGENT_SPEC[7], "ok", 100, "%s 符号 · %s" % (symbols, size_text)))
        else:
            pct = clamp_pct((symbols or 0) / 524.0 * 100) if symbols else 0
            agents.append(make_agent(*AGENT_SPEC[7], "warn", pct, "%s 符号 · %s" % (symbols if symbols else "?", size_text)))

    # u1-verify
    if not mac["ok"]:
        agents.append(make_agent(*AGENT_SPEC[8], "down", 0, "MAC 不可达"))
    else:
        checked = u1.get("checked")
        matched = u1.get("matched")
        at_epoch = u1.get("gen_epoch") or u1.get("mtime")
        if checked and matched is not None:
            ok = matched == checked
            pct = clamp_pct(matched / float(checked) * 100, floor=0) if checked else 0
            agents.append(make_agent(*AGENT_SPEC[8], "ok" if ok else "warn", pct,
                                     "%s/%s 一致 · %s" % (matched, checked, local_hhmm(at_epoch))))
        else:
            agents.append(make_agent(*AGENT_SPEC[8], "unknown", 50, "无校验报告"))

    # duckdb (WIN)
    full_verify = win.get("full_verify") or {}
    duck = win.get("duckdb") or {}
    if duck.get("bytes"):
        rows = full_verify.get("klines")
        building = bool(full_verify.get("mtime") and duck.get("mtime") and duck["mtime"] > full_verify["mtime"] + 90)
        if full_verify:
            state, pct = "ok", 100 if not building else 85
            note = "%s 行 · %s%s" % (fmt_count(rows), fmt_gib(duck.get("bytes")), "·构建中" if building else "")
        else:
            state, pct = "ok", 80
            note = "%s · 构建中" % fmt_gib(duck.get("bytes"))
        agents.append(make_agent(*AGENT_SPEC[9], state, pct, note))
    else:
        agents.append(make_agent(*AGENT_SPEC[9], "unknown", 50, "研究库未知"))

    # backup (HK)
    if not hk["ok"]:
        agents.append(make_agent(*AGENT_SPEC[10], "down", 0, "HK 不可达"))
    else:
        age = hk.get("age")
        du_kb_hk = hk.get("du_kb")
        if age is not None and age <= 3600 and du_kb_hk is not None:
            state, pct = "ok", 100
        else:
            state = "warn"
            pct = clamp_pct(100 - max(0.0, (age or 0) - 3600) / 3600.0 * 20)
        note = "%s · %s 前" % (fmt_size_mib(du_kb_hk * 1024) if du_kb_hk is not None else "?",
                               fmt_age(age))
        agents.append(make_agent(*AGENT_SPEC[10], state, pct, note))

    # research (WIN)
    raw = win.get("raw") or {}
    fapi = win.get("fapi") or {}
    if raw.get("bytes") and fapi.get("files"):
        note = "raw %s · fapi %s 件" % (fmt_gib(raw.get("bytes")), fapi.get("files"))
        agents.append(make_agent(*AGENT_SPEC[11], "ok", 100, note))
    else:
        agents.append(make_agent(*AGENT_SPEC[11], "warn", 70, "研究数据不完整"))

    return agents


def build_activity(mac, sg, hk, win, now, limit=16):
    """12-16 条真实事件（最新在前）；来源：Mac git log/BOARD/u1、SG timer/journal、HK 备份、WIN 构建产物。"""
    events = []

    def add(epoch, eid, who, title, state):
        if epoch is None:
            return
        try:
            epoch = int(float(epoch))
        except (TypeError, ValueError):
            return
        events.append({
            "epoch": epoch,
            "id": eid,
            "who": who,
            "title": trunc(title, 40),
            "state": state if state in ("done", "run", "warn") else "done",
            "age_s": max(0, int(now - epoch)),
            "at": local_hhmm(epoch),
        })

    # --- Mac：git 最近 6 条 commit ---
    for commit in (mac.get("git", {}).get("log") or [])[:6]:
        add(commit.get("ct"), "mac-git-%s" % commit.get("h"), "MAC", commit.get("subject"), "done")

    # --- Mac：BOARD / u1 校验 / u1 全量下载 / fapi ---
    add(mac.get("board_mtime"), "mac-board", "MAC", "BOARD 同步 claim 口径", "done")
    u1 = mac.get("u1") or {}
    if u1.get("checked") and u1.get("matched") is not None:
        state = "done" if u1["matched"] == u1["checked"] else "warn"
        add(u1.get("gen_epoch") or u1.get("mtime"), "mac-u1-verify", "MAC",
            "U1 校验 %s/%s 一致" % (u1["matched"], u1["checked"]), state)
    if u1.get("symbols"):
        add(u1.get("full_manifest_epoch"), "mac-u1-full", "MAC",
            "U1 全量下载 %s 符号" % u1["symbols"], "done")
    if u1.get("fapi_symbols"):
        add(u1.get("fapi_epoch"), "mac-u1-fapi", "MAC",
            "U1 fapi 30d 采集 %s 符号" % u1["fapi_symbols"], "done")

    # --- SG：采集 / 聚合 / 衍生 / agent-service ---
    timers = sg.get("timers") or {}
    if sg["ok"]:
        collector_epoch = sg.get("collector_log_ts")
        add(collector_epoch, "sg-collector", "SG", "采集器 15s 轮询 1m bar", "run")
        add(timers.get("aggregate_ts"), "sg-aggregate", "SG", "聚合 5m/15m/1h 完成", "done")
        add(timers.get("futures_ts") or sg.get("futures_log_ts"), "sg-futures", "SG",
            "衍生采集 OI/taker/funding", "warn" if sg.get("futures_bad") else "done")
        health = sg.get("health") or {}
        uptime = health.get("uptime_s") if isinstance(health, dict) else None
        if uptime:
            add(now - float(uptime), "sg-agent-svc", "SG", "agent-service 常驻 8710", "run")

    # --- HK：备份 ---
    if hk.get("ok"):
        state = "done" if (hk.get("age") or 0) <= 3600 else "warn"
        add(hk.get("latest_ts"), "hk-backup", "HK",
            "备份同步 %s" % (fmt_size_mib((hk.get("du_kb") or 0) * 1024) if hk.get("du_kb") else "?"), state)

    # --- WIN：raw / fapi / duckdb / 辅助数据装载 / u1 建库 / git ---
    raw = win.get("raw") or {}
    if raw.get("bytes"):
        add(raw.get("mtime"), "win-raw", "WIN", "raw 全量下载 %s" % fmt_gib(raw.get("bytes")), "done")
    fapi = win.get("fapi") or {}
    if fapi.get("files"):
        add(fapi.get("mtime"), "win-fapi", "WIN", "fapi 衍生文件 %s 件" % fapi["files"], "done")
    full_verify = win.get("full_verify") or {}
    if full_verify:
        add(full_verify.get("mtime"), "win-duckdb", "WIN",
            "DuckDB 全量构建 %s 行" % fmt_count(full_verify.get("klines")), "done")
    aux = win.get("aux_load") or {}
    if aux:
        add(win.get("aux_mtime"), "win-aux", "WIN",
            "辅助数据装载 OI/taker/funding", "done")
    bmf = win.get("build_manifest_full") or {}
    if bmf.get("pairs_count"):
        add(bmf.get("mtime"), "win-u1-build", "WIN",
            "U1 建库 %s 对 5m" % bmf["pairs_count"], "done")
    for commit in (win.get("git", {}).get("log") or [])[:2]:
        add(commit.get("ct"), "win-git-%s" % commit.get("h"), "WIN", commit.get("subject"), "done")

    # 按时间倒序、id 去重，取最近 limit 条
    seen = set()
    unique = []
    for ev in sorted(events, key=lambda item: item["epoch"], reverse=True):
        if ev["id"] in seen:
            continue
        seen.add(ev["id"])
        unique.append(ev)
    trimmed = unique[:limit]
    for ev in trimmed:
        ev.pop("epoch", None)
    return trimmed


# ---------------------------------------------------------------------------
# 单次采集
# ---------------------------------------------------------------------------

def _win_collect_timed():
    wind_started = time.time()
    payload = win_collect()
    payload["took_s"] = round(time.time() - wind_started, 2)
    return payload


def collect_once():
    started = time.time()
    errors = []
    alerts = []

    with ThreadPoolExecutor(max_workers=4) as pool:
        fut_win = pool.submit(_win_collect_timed)
        fut_mac = pool.submit(run_probe_safe, "mac", "mac_probe.py", MAC_KEY, MAC_HOST, MAC_TIMEOUT)
        fut_sg = pool.submit(run_sg_probe)
        fut_hk = pool.submit(run_probe_safe, "hk", "hk_probe.py", HK_KEY, HK_HOST, HK_TIMEOUT)

        try:
            win_payload = fut_win.result()
        except Exception as exc:  # noqa: BLE001
            win_payload = None
            errors.append("win: 本地采集异常 %s" % short(exc))
        r_mac = fut_mac.result()
        r_sg = fut_sg.result()
        r_hk = fut_hk.result()

    log("probe win %s %.2fs" % (
        "ok" if win_payload is not None else "error",
        (win_payload or {}).get("took_s", 0.0),
    ))
    for name, res in (("mac", r_mac), ("sg", r_sg), ("hk", r_hk)):
        log("probe %s %s %.2fs%s" % (
            name, res["status"], res.get("secs", 0.0),
            "" if res["status"] == "ok" else " (" + res.get("error", "") + ")",
        ))

    mac = build_mac_ctx(r_mac)
    sg = build_sg_ctx(r_sg)
    hk = build_hk_ctx(r_hk)
    win = win_payload if isinstance(win_payload, dict) else {}
    now = time.time()

    # ---- 采集错误归集 ----
    for name, res in (("mac", r_mac), ("sg", r_sg), ("hk", r_hk)):
        if res["status"] != "ok":
            errors.append("%s: %s" % (name, short(res.get("error", "未知错误"))))
    if win.get("token_errors"):
        errors.append("win: token 缓存解析失败 %s 个" % win["token_errors"])
    for warning in win.get("warnings") or []:
        errors.append("win: " + short(warning))
    if mac.get("token_errors"):
        errors.append("mac: token 缓存解析失败 %s 个" % mac["token_errors"])
    mac_git = mac.get("git") or {}
    if mac_git.get("error"):
        errors.append("mac: git 读取失败 %s" % short(mac_git["error"]))
    sg_health = sg.get("health")
    if sg["ok"] and not isinstance(sg_health, dict):
        errors.append("sg: /health 不可用 %s" % short(((r_sg.get("payload") or {}).get("health_error") or "")))
    if sg["ok"] and (r_sg.get("payload") or {}).get("bars_meta", {}).get("err"):
        errors.append("sg: bars COUNT 失败 %s" % short((r_sg.get("payload") or {}).get("bars_meta", {}).get("err")))
    hk_payload = r_hk.get("payload") or {}
    if hk["ok"] and hk_payload.get("du_rc") != 0:
        errors.append("hk: du 失败 %s" % short(hk_payload.get("du_error") or ""))
    if r_sg.get("payload", {}).get("claim_index_meta", {}).get("err"):
        errors.append("sg: claim 索引 COUNT 失败 %s" % short(r_sg["payload"]["claim_index_meta"]["err"]))

    # ---- WIN 节点 ----
    raw = win.get("raw") or {}
    duck = win.get("duckdb") or {}
    fapi = win.get("fapi") or {}
    full_verify = win.get("full_verify") or {}
    u1_files = win.get("u1_files") or []
    if win:
        win_state = "ok" if raw.get("bytes") is not None and duck.get("bytes") is not None else "warn"
        win_node = make_node(
            "win", "WIN", "研究", win_state,
            "raw %s · duckdb %s" % (fmt_gib(raw.get("bytes")), fmt_gib(duck.get("bytes"))),
            "u1 %s 对 · fapi %s 件" % (full_verify.get("klines_symbols") or len(u1_files), fapi.get("files") or 0),
        )
        log("win raw=%s files=%s duckdb=%sB u1=%s fapi=%s git=%s" % (
            raw.get("bytes"), raw.get("files"), duck.get("bytes"), len(u1_files),
            fapi.get("files"), (win.get("git") or {}).get("head") or "?",
        ))
    else:
        win_node = make_node("win", "WIN", "研究", "warn", "本地采集失败", "")
        errors.append("win: 本地数据采集失败")

    # ---- MAC 节点 ----
    mac_git = mac.get("git") or {}
    head = mac_git.get("head") or "?"
    commit_at = local_hhmm(mac_git.get("commit_ct"))
    u1 = mac.get("u1") or {}
    checked = u1.get("checked")
    matched = u1.get("matched")
    dsh = mac.get("dsh") or {}
    dsh_text = "DSH 在线" if dsh.get("running") else "DSH 离线"
    if mac["ok"]:
        if checked is not None and matched is not None:
            f2 = "u1 %s/%s · %s" % (matched, checked, dsh_text)
        else:
            f2 = "u1 ? · %s" % dsh_text
        mac_state = "ok" if head != "?" and dsh.get("running") else "warn"
        if mac_git.get("dirty"):
            mac_state = "warn"
        mac_node = make_node("mac", "MAC", "开发", mac_state, "HEAD %s · %s" % (head, commit_at), f2)
    elif r_mac["status"] == "down":
        mac_node = make_node("mac", "MAC", "开发", "down", "不可达", "")
        alerts.append({"level": "bad", "text": "MAC 不可达 · 跨机实况降级"})
    else:
        mac_node = make_node("mac", "MAC", "开发", "unknown", "探针异常", "")

    # ---- SG 节点 ----
    bars = sg.get("bars") or {}
    units_text = "?"
    if sg.get("units_total"):
        units_text = "%s/%s" % (sg.get("units_ok"), sg.get("units_total"))
    if sg["ok"]:
        sg_state = "ok"
        if sg["futures_bad"]:
            sg_state = "warn"
            lag_rep = futures_lag_rep(sg["health"])
            text = "SG crypto-futures 失败"
            if lag_rep is not None:
                text += " · 衍生数据滞后 %s" % fmt_lag(lag_rep)
            alerts.append({"level": "warn", "text": text})
        if sg["lag"] is not None and sg["lag"] > 120:
            sg_state = "warn"
            alerts.append({"level": "warn", "text": "SG 主数据滞后 %s" % fmt_lag(sg["lag"])})
        if sg["htf15"] is not None and sg["htf15"] > 1200:
            sg_state = "warn"
            alerts.append({"level": "warn", "text": "SG HTF 15m 滞后 %.0fs" % sg["htf15"]})
        if not isinstance(sg_health, dict):
            sg_state = "warn"
            alerts.append({"level": "warn", "text": "SG health 端点无响应"})
        sg_node = make_node(
            "sg", "SG", "采集", sg_state,
            "lag %s · units %s" % (fmt_lag(sg["lag"]) if sg["lag"] is not None else "?", units_text),
            "bars %s · disk %s" % (fmt_count(bars.get("m1")), fmt_disk_g(sg.get("disk_kb"))),
        )
        log("sg lag=%s htf15=%s futures_bad=%s units=%s bars m1=%s m5=%s m15=%s h1=%s disk_kb=%s mem_kb=%s" % (
            sg["lag"], sg["htf15"], sg["futures_bad"], units_text,
            bars.get("m1"), bars.get("m5"), bars.get("m15"), bars.get("h1"),
            sg.get("disk_kb"), sg.get("mem_kb"),
        ))
    elif r_sg["status"] == "down":
        sg_node = make_node("sg", "SG", "采集", "down", "不可达", "")
        alerts.append({"level": "bad", "text": "SG 不可达 · 实时采集降级"})
    else:
        sg_node = make_node("sg", "SG", "采集", "unknown", "探针异常", "")

    # ---- HK 节点 ----
    if hk["ok"]:
        hk_state = "ok"
        if hk.get("age") is not None and hk["age"] > 3600:
            hk_state = "warn"
            alerts.append({"level": "warn", "text": "HK 备份滞后 %s" % fmt_age(hk["age"])})
        hk_node = make_node(
            "hk", "HK", "备份", hk_state,
            "/srv %s · %s 前" % (
                fmt_size_mib(hk["du_kb"] * 1024) if hk.get("du_kb") is not None else "?",
                fmt_age(hk.get("age")),
            ),
            "disk %s" % fmt_disk_g(hk.get("disk_kb")),
        )
        log("hk du_kb=%s latest_age=%s disk_kb=%s" % (hk.get("du_kb"), fmt_age(hk.get("age")), hk.get("disk_kb")))
    elif r_hk["status"] == "down":
        hk_node = make_node("hk", "HK", "备份", "down", "不可达", "")
        alerts.append({"level": "bad", "text": "HK 不可达 · 备份状态未知"})
    else:
        hk_node = make_node("hk", "HK", "备份", "unknown", "探针异常", "")

    # ---- claims（Mac BOARD 全档） ----
    claims = {"total": None, "verified": None, "refuted": None, "contested": None,
              "method": None, "hypothesis": None, "parked": None}
    mac_claims = mac.get("claims")
    if isinstance(mac_claims, dict) and mac_claims.get("total") is not None:
        for key in claims:
            claims[key] = mac_claims.get(key)
    # SG claim 索引与 BOARD 差值告警（真实同步滞后）
    claim_index = sg.get("claim_index") or {}
    if isinstance(claims.get("total"), int) and isinstance(claim_index.get("total"), int) \
            and claim_index["total"] < claims["total"]:
        diff = claims["total"] - claim_index["total"]
        alerts.append({"level": "warn", "text": "SG claim 索引 %s/%s · 差 %s 条未同步" % (
            claim_index["total"], claims["total"], diff)})

    # ---- progress ----
    progress = {"u1": "—", "commit": "", "commit_at": ""}
    if mac["ok"]:
        if head != "?":
            progress["commit"] = head
            progress["commit_at"] = commit_at
        if checked is not None and matched is not None:
            progress["u1"] = "%s/%s @%s" % (matched, checked, local_hhmm(u1.get("gen_epoch") or u1.get("mtime")))

    # ---- tokens（Win 本地 + Mac 远端） ----
    win_tokens = win.get("tokens") or dict(TOKEN_ZERO)
    mac_tokens = mac.get("tokens") or dict(TOKEN_ZERO)
    if not mac["ok"]:
        errors.append("mac: token 用量不可用（节点不可达）")
    total_tokens = {
        "inputTokens": int(win_tokens.get("inputTokens", 0)) + int(mac_tokens.get("inputTokens", 0)),
        "outputTokens": int(win_tokens.get("outputTokens", 0)) + int(mac_tokens.get("outputTokens", 0)),
        "cacheReadTokens": int(win_tokens.get("cacheReadTokens", 0)) + int(mac_tokens.get("cacheReadTokens", 0)),
    }
    total_tokens["allTokens"] = (
        total_tokens["inputTokens"] + total_tokens["outputTokens"] + total_tokens["cacheReadTokens"]
    )
    tokens = {"win": win_tokens, "mac": mac_tokens, "total": total_tokens}
    log("tokens win sessions=%s in=%s out=%s cacheRead=%s | mac sessions=%s in=%s out=%s cacheRead=%s | total all=%s" % (
        win_tokens.get("sessions"), fmt_tokens(win_tokens.get("inputTokens")),
        fmt_tokens(win_tokens.get("outputTokens")), fmt_tokens(win_tokens.get("cacheReadTokens")),
        mac_tokens.get("sessions"), fmt_tokens(mac_tokens.get("inputTokens")),
        fmt_tokens(mac_tokens.get("outputTokens")), fmt_tokens(mac_tokens.get("cacheReadTokens")),
        fmt_tokens(total_tokens["allTokens"]),
    ))

    # ---- metrics（全部来自真实采集；拿不到给 null） ----
    metrics = {
        "bars": {
            "m1": bars.get("m1"),
            "m5": bars.get("m5"),
            "m15": bars.get("m15"),
            "h1": bars.get("h1"),
        },
        "u1": {
            "symbols": u1.get("symbols"),
            "size_mb": int(round((u1.get("du_kb") or 0) / 1024.0)) if u1.get("du_kb") else None,
            "checked": checked,
            "matched": matched,
            "at": local_hhmm(u1.get("gen_epoch") or u1.get("mtime")) if u1 else None,
        },
        "sg": {
            "data_lag_s": sg.get("lag"),
            "htf15_lag_s": sg.get("htf15"),
            "futures_fresh": sg.get("futures_fresh"),
            "data_fresh": sg.get("data_fresh"),
            "disk_free_g": int(round((sg.get("disk_kb") or 0) / 1048576.0)) if sg.get("disk_kb") else None,
            "mem_free_g": round((sg.get("mem_kb") or 0) / 1048576.0, 1) if sg.get("mem_kb") else None,
            "units_ok": sg.get("units_ok"),
            "units_total": sg.get("units_total"),
        },
        "hk": {
            "backup_mb": int(round((hk.get("du_kb") or 0) / 1024.0)) if hk.get("du_kb") is not None else None,
            "age_s": int(hk["age"]) if hk.get("age") is not None else None,
            "disk_free_g": int(round((hk.get("disk_kb") or 0) / 1048576.0)) if hk.get("disk_kb") else None,
        },
        "win": {
            "raw_gb": round(raw["bytes"] / 1073741824.0, 1) if raw.get("bytes") is not None else None,
            "duckdb_gb": round(duck["bytes"] / 1073741824.0, 1) if duck.get("bytes") is not None else None,
            "u1_files": len(u1_files) if win else None,
            "fapi_files": fapi.get("files"),
        },
        "mac": {
            "head": head if mac["ok"] else None,
            "head_at": commit_at if mac["ok"] else None,
            "dirty": mac_git.get("dirty") if mac["ok"] else None,
            "dsh": bool(dsh.get("running")) if mac["ok"] else None,
        },
    }
    if bars.get("m1") is None:
        alerts.append({"level": "warn", "text": "SG bars COUNT 不可用 · 大表超时"})

    # ---- agents / activity ----
    agents = build_agents(mac, sg, hk, win, now)
    activity = build_activity(mac, sg, hk, win, now)

    took_ms = int(round((time.time() - started) * 1000))
    live = {
        "schema": "agent-live/2",
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "epoch": int(time.time()),
        "collect": {"ok": len(errors) == 0, "took_ms": took_ms, "errors": errors},
        "nodes": [win_node, mac_node, sg_node, hk_node],
        "claims": claims,
        "progress": progress,
        "tokens": tokens,
        "metrics": metrics,
        "agents": agents,
        "activity": activity,
        "alerts": alerts,
    }
    write_live(live)
    node_summary = " ".join("%s=%s" % (n["id"], n["state"]) for n in live["nodes"])
    agent_summary = " ".join("%s=%s/%s" % (a["id"], a["state"], a["pct"]) for a in live["agents"])
    log("run ok=%s took_ms=%s nodes=[%s] agents=[%s] activity=%d alerts=%d errors=%d" % (
        live["collect"]["ok"], took_ms, node_summary, agent_summary,
        len(activity), len(alerts), len(errors),
    ))
    for err in errors:
        log("error: " + err)
    for alert in alerts:
        log("alert[%s] %s" % (alert["level"], alert["text"]))
    return live


def build_hk_ctx(r_hk):
    ctx = {"ok": r_hk["status"] == "ok", "host": None, "now": None, "du_kb": None,
           "latest_ts": None, "disk_kb": None, "age": None}
    if not ctx["ok"]:
        return ctx
    payload = r_hk["payload"]
    ctx["host"] = payload.get("host")
    ctx["now"] = payload.get("now")
    ctx["du_kb"] = payload.get("du_kb")
    latest_ts = payload.get("latest_ts")
    ctx["latest_ts"] = safe_float(latest_ts)
    ctx["disk_kb"] = payload.get("disk_avail_kb")
    now_ts = safe_float(payload.get("now"))
    if ctx["latest_ts"] is not None and now_ts is not None:
        ctx["age"] = max(0.0, now_ts - ctx["latest_ts"])
    return ctx


def write_live(live):
    text = json.dumps(live, ensure_ascii=False, indent=2) + "\n"
    with open(TMP_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(str(TMP_PATH), str(OUT_PATH))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    utf8_console()
    parser = argparse.ArgumentParser(description="crypto-agent 跨机实况采集器 v2（只读）")
    parser.add_argument("--loop", type=float, metavar="SEC", default=None,
                        help="循环采集间隔秒数（如 15）；缺省只跑一次")
    parser.add_argument("--once", action="store_true", help="只采集一次（默认行为）")
    args = parser.parse_args(argv)

    try:
        if args.loop is not None:
            interval = max(1.0, float(args.loop))
            log("collector start: loop interval=%ss out=%s ssh=%s" % ("%g" % interval, OUT_PATH, SSH))
            try:
                while True:
                    cycle_started = time.time()
                    try:
                        collect_once()
                    except Exception as exc:  # noqa: BLE001
                        log("collect crashed: %r" % (exc,))
                    # 固定节拍：按采集开始时间对齐，避免采集耗时叠加导致超过页面 15s 刷新周期
                    wait = interval - (time.time() - cycle_started)
                    time.sleep(max(1.0, wait))
            except KeyboardInterrupt:
                log("collector stopped: KeyboardInterrupt")
                return 0
        else:
            collect_once()
        return 0
    finally:
        close_sg_probe()


if __name__ == "__main__":
    sys.exit(main())
