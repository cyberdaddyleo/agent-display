# -*- coding: utf-8 -*-
"""SG 只读探针 v2：Win 直连 ssh root@SG "python3 -" 从 stdin 执行，远端不落文件。

输出格式：@@LIVE_JSON_BEGIN@@ / 单行 JSON / @@LIVE_JSON_END@@
只读：systemctl 查询、HTTP GET /health、journalctl 读最近日志、df/free、SQLite 只读 COUNT。

v2 新增：
- bars 真实 COUNT（1m/5m/15m/1h）+ 最新 close_time；SQLite 进度回调限时，超时置 null 不阻塞整体
- 三个 timer 的 LastTriggerUSec（转 epoch）
- claim-index.db 状态分布（校验 BOARD claim 是否已索引）
- collector / futures 最近一条 journal 时间
"""
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request

BEGIN = "@@LIVE_JSON_BEGIN@@"
END = "@@LIVE_JSON_END@@"

DB_HOT = "/srv/crypto-agent/data/hot/market.db"
DB_CLAIM = "/srv/crypto-agent/data/cold/claim-index.db"
COUNT_BUDGET_S = 7.0  # SQLite COUNT 预算；外层 SSH 超时 12s


def run(args, timeout=8):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return {
            "rc": p.returncode,
            "out": p.stdout.decode("utf-8", "replace").strip(),
            "err": p.stderr.decode("utf-8", "replace").strip()[:300],
        }
    except Exception as exc:  # noqa: BLE001
        return {"rc": 127, "out": "", "err": type(exc).__name__ + ": " + str(exc)[:250]}


def parse_df_avail_kb(out):
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    parts = lines[1].split()
    if len(parts) < 4:
        return None
    try:
        return int(parts[3])
    except ValueError:
        return None


def parse_free_avail_kb(out):
    for line in out.splitlines():
        if line.strip().startswith("Mem:"):
            parts = line.split()
            if len(parts) >= 7:
                try:
                    return int(parts[6])
                except ValueError:
                    return None
    return None


def parse_units(out):
    units = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("UNIT") or line.startswith("0 units"):
            continue
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        if not parts[0].startswith("crypto-"):
            continue
        units.append({
            "unit": parts[0],
            "load": parts[1],
            "active": parts[2],
            "sub": parts[3],
        })
    return units


def sqlite_rows_query(db, sql, params=(), budget=6.0):
    """只读打开 SQLite 执行单条查询；超过 budget 秒用进度回调中断 -> {'err': ...}。"""
    started = time.time()
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=2.0)
    except Exception as exc:  # noqa: BLE001
        return {"err": "open: " + str(exc)[:120]}
    try:
        cur = con.cursor()

        def handler():
            return 1 if time.time() - started > budget else 0

        con.set_progress_handler(handler, 50000)
        cur.execute(sql, params)
        rows = cur.fetchall()
        return {"rows": rows, "secs": round(time.time() - started, 2)}
    except Exception as exc:  # noqa: BLE001
        return {"err": type(exc).__name__ + ": " + str(exc)[:120], "secs": round(time.time() - started, 2)}
    finally:
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass


def bars_metrics():
    out = {"m1": None, "m5": None, "m15": None, "h1": None, "latest": {}}
    res = sqlite_rows_query(
        DB_HOT,
        "SELECT interval, COUNT(*), MAX(close_time) FROM bars GROUP BY interval",
        budget=COUNT_BUDGET_S,
    )
    if "err" in res:
        return out, res
    mapping = {"1m": "m1", "5m": "m5", "15m": "m15", "1h": "h1"}
    for interval, count, close_ms in res["rows"]:
        key = mapping.get(str(interval))
        if key is None:
            continue
        try:
            out[key] = int(count)
        except (TypeError, ValueError):
            pass
        if close_ms is not None:
            try:
                out["latest"][key] = int(close_ms) // 1000
            except (TypeError, ValueError):
                pass
    return out, res


def claim_index_metrics():
    out = {"total": None, "status": {}}
    res = sqlite_rows_query(DB_CLAIM, "SELECT status, COUNT(*) FROM claims GROUP BY status", budget=3.0)
    if "err" in res:
        return out, res
    total = 0
    for status, count in res["rows"]:
        try:
            n = int(count)
        except (TypeError, ValueError):
            continue
        out["status"][str(status)] = n
        total += n
    out["total"] = total
    return out, res


def timer_trigger_epoch(unit):
    r = run(["systemctl", "show", "-p", "LastTriggerUSec", "--value", unit], timeout=5)
    text = r["out"].strip()
    if not text or text in ("n/a", ""):
        return None
    r2 = run(["date", "-d", text, "+%s"], timeout=5)
    if r2["rc"] == 0 and r2["out"].isdigit():
        return int(r2["out"])
    return None


def journal_last_epoch(unit):
    r = run(["journalctl", "-u", unit, "-n", "1", "--no-pager", "-o", "short-unix"], timeout=6)
    for line in r["out"].splitlines():
        token = line.split(None, 1)[0] if line.strip() else ""
        try:
            return int(float(token))
        except (TypeError, ValueError):
            continue
    return None


def main():
    payload = {
        "host": run(["hostname"])["out"],
        "now": int(time.time()),
    }

    # bars COUNT（大表 ~2.7s）与 health（~0.7s）并行，压缩探针总时长
    import threading
    bars_box = {}

    def bars_worker():
        bars_box["bars"], bars_box["meta"] = bars_metrics()

    bars_thread = threading.Thread(target=bars_worker, daemon=True)
    bars_thread.start()

    r = run(["systemctl", "list-units", "crypto-*", "--plain", "--no-legend", "--no-pager"])
    units = parse_units(r["out"])
    healthy = 0
    for u in units:
        if u["active"] not in ("failed", "inactive") and u["sub"] not in ("failed", "dead"):
            healthy += 1
    payload["units_rc"] = r["rc"]
    payload["units"] = units
    payload["units_total"] = len(units)
    payload["units_ok"] = healthy

    r = run(["systemctl", "show", "-p", "ActiveState", "-p", "SubState", "-p", "Result", "crypto-futures.service"], timeout=5)
    futures_unit = {}
    for line in r["out"].splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            futures_unit[k] = v
    payload["futures_unit"] = futures_unit
    payload["crypto_futures_failed"] = (
        futures_unit.get("ActiveState") == "failed" or futures_unit.get("Result") == "failed"
    )

    try:
        req = urllib.request.Request("http://127.0.0.1:8710/health", headers={"User-Agent": "live-probe"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            raw = resp.read().decode("utf-8", "replace")
        payload["health"] = json.loads(raw)
        payload["health_error"] = None
    except Exception as exc:  # noqa: BLE001
        payload["health"] = None
        payload["health_error"] = type(exc).__name__ + ": " + str(exc)[:200]

    bars_thread.join(COUNT_BUDGET_S + 3.0)
    bars = bars_box.get("bars") or {"m1": None, "m5": None, "m15": None, "h1": None, "latest": {}}
    bars_meta = bars_box.get("meta") or {"err": "bars 线程超时"}
    payload["bars"] = bars
    payload["bars_meta"] = {"err": bars_meta.get("err")} if "err" in bars_meta else {"secs": bars_meta.get("secs")}

    claims, claim_meta = claim_index_metrics()
    payload["claim_index"] = claims
    payload["claim_index_meta"] = {"err": claim_meta.get("err")} if "err" in claim_meta else {"secs": claim_meta.get("secs")}

    payload["timers"] = {
        "aggregate_ts": timer_trigger_epoch("crypto-aggregate.timer"),
        "backup_ts": timer_trigger_epoch("crypto-backup.timer"),
        "futures_ts": timer_trigger_epoch("crypto-futures.timer"),
    }
    payload["collector_log_ts"] = journal_last_epoch("crypto-collector.service")
    payload["futures_log_ts"] = journal_last_epoch("crypto-futures.service")

    r = run(["df", "-k", "/"])
    payload["df_rc"] = r["rc"]
    payload["disk_avail_kb"] = parse_df_avail_kb(r["out"])

    r = run(["free", "-k"])
    payload["free_rc"] = r["rc"]
    payload["mem_avail_kb"] = parse_free_avail_kb(r["out"])

    try:
        payload["db_bytes"] = os.path.getsize(DB_HOT)
    except OSError:
        payload["db_bytes"] = None

    return payload


def emit(obj):
    sys.stdout.write(BEGIN + "\n")
    sys.stdout.write(json.dumps(obj, ensure_ascii=True, separators=(",", ":")) + "\n")
    sys.stdout.write(END + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    try:
        emit(main())
    except Exception as exc:  # noqa: BLE001
        emit({"probe_error": type(exc).__name__ + ": " + str(exc)[:300]})
