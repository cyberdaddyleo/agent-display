# -*- coding: utf-8 -*-
"""Mac 中转探针模板：经 ssh stdin 管道送到 Mac 后由 python3 执行。

作用：在同一个 Win->Mac SSH 会话里并发执行 SG/HK 探针。
  - 内层命令：ssh -o BatchMode=yes -o ConnectTimeout=6 -T eth-sg python3 - <- 探针源码（stdin 管道）
  - 不在 Mac/SG/HK 落任何文件；内层 ssh 不带 -n，显式接收 stdin。
  - SG/HK 各自 12s subprocess 超时 + try/except，单源失败不影响另一源。

本文件是模板：采集器运行时会用 JSON 字符串字面量替换下方 SG_SRC / HK_SRC 的占位符，
组装后的脚本整体通过 ssh ... "python3 -" 送入 Mac，远端不存盘。
"""
import json
import subprocess
import sys
import threading
import time

BEGIN = "@@LIVE_JSON_BEGIN@@"
END = "@@LIVE_JSON_END@@"

SG_SRC = __SG_SRC__
HK_SRC = __HK_SRC__

SG_CMD = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", "-T", "eth-sg", "python3", "-"]
HK_CMD = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", "-T", "eth-hk", "python3", "-"]
TIMEOUT = 12


def extract_payload(text):
    start = text.find(BEGIN)
    end = text.find(END)
    if start < 0 or end < 0 or end <= start:
        return None
    try:
        return json.loads(text[start + len(BEGIN):end].strip())
    except ValueError:
        return None


def run_one(name, cmd, src, timeout=TIMEOUT):
    result = {"status": "error", "error": None, "secs": 0.0}
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            input=src.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        secs = round(time.time() - started, 2)
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace").strip()
        payload = extract_payload(out)
        if payload is not None and isinstance(payload, dict) and payload.get("probe_error"):
            result.update(status="error", error="远端探针异常: " + str(payload["probe_error"])[:200], secs=secs)
        elif proc.returncode == 255:
            result.update(status="down", error="SSH 连接失败: " + (err or "rc=255")[:200], secs=secs)
        elif proc.returncode != 0:
            result.update(status="error", error="远端退出码 %s: %s" % (proc.returncode, (err or out)[:200]), secs=secs)
        elif payload is None:
            result.update(status="error", error="探针输出无法解析: " + (err or out)[:200], secs=secs)
        elif not isinstance(payload, dict):
            result.update(status="error", error="探针输出不是 JSON 对象", secs=secs)
        else:
            result.update(status="ok", payload=payload, secs=secs)
    except subprocess.TimeoutExpired:
        result.update(status="down", error="SSH 超时 %ss" % timeout, secs=round(time.time() - started, 2))
    except Exception as exc:  # noqa: BLE001
        result.update(status="error", error="中转异常: %s" % str(exc)[:200], secs=round(time.time() - started, 2))
    return result


def main():
    results = {}
    threads = []

    def worker(name, cmd, src):
        results[name] = run_one(name, cmd, src)

    for name, cmd, src in (("sg", SG_CMD, SG_SRC), ("hk", HK_CMD, HK_SRC)):
        th = threading.Thread(target=worker, args=(name, cmd, src))
        th.daemon = True
        th.start()
        threads.append(th)
    for th in threads:
        th.join(TIMEOUT + 3)
    return results


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
