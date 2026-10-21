# -*- coding: utf-8 -*-
"""HK 只读探针 v2：Win 直连 ssh root@HK "python3 -" 从 stdin 执行，远端不落文件。

输出格式：@@LIVE_JSON_BEGIN@@ / 单行 JSON / @@LIVE_JSON_END@@
只读（du/find/df）。HK 无 crypto-* systemd unit，不采集 unit。
"""
import json
import subprocess
import sys
import time

BEGIN = "@@LIVE_JSON_BEGIN@@"
END = "@@LIVE_JSON_END@@"


def run(args, timeout=9):
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


def main():
    payload = {
        "host": run(["hostname"])["out"],
        "now": int(time.time()),
    }

    r = run(["du", "-sk", "/srv/crypto-agent"], timeout=10)
    du_kb = None
    if r["rc"] == 0 and r["out"]:
        try:
            du_kb = int(r["out"].split()[0])
        except (IndexError, ValueError):
            du_kb = None
    payload["du_rc"] = r["rc"]
    payload["du_kb"] = du_kb
    payload["du_error"] = r["err"] if r["rc"] != 0 else None

    # 最新备份时间 = /srv/crypto-agent 下所有文件 mtime 的最大值（epoch 秒）
    cmd = (
        "find /srv/crypto-agent -type f -printf '%T@\\n' 2>/dev/null "
        "| sort -n | tail -1"
    )
    r = run(["sh", "-c", cmd], timeout=10)
    latest_ts = None
    if r["rc"] == 0 and r["out"]:
        try:
            latest_ts = float(r["out"].splitlines()[0])
        except (IndexError, ValueError):
            latest_ts = None
    payload["latest_rc"] = r["rc"]
    payload["latest_ts"] = latest_ts

    r = run(["df", "-k", "/"])
    payload["df_rc"] = r["rc"]
    payload["disk_avail_kb"] = parse_df_avail_kb(r["out"])

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
