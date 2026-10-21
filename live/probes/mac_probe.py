# -*- coding: utf-8 -*-
"""Mac 只读探针 v2：通过 ssh ... "python3 -" 从 stdin 执行，不在远端落任何文件。

输出格式：@@LIVE_JSON_BEGIN@@ / 单行 JSON / @@LIVE_JSON_END@@
仅标准库；只读（git 查询、读文件、pgrep、du）。v2 新增：token 用量、BOARD claim 全档、
BOARD 任务行、u1 资产体积/符号数、fapi manifest、BOARD mtime、Git 最近 6 条 commit。
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

BEGIN = "@@LIVE_JSON_BEGIN@@"
END = "@@LIVE_JSON_END@@"

CWD_FILTER = "/Users/sen/look"  # 本项目（Agent 战术大屏）在 Mac 侧的工作目录
BOARD_IDS = ("r0zCvK", "r1xplE", "r9mvKm", "rnX7iJ", "reAXrz", "rFD2gJ",
             "rLEieg", "r7KnPv", "rVf9Tm", "rWg8Hn", "rltDxr", "rPS8Ls")


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


def strip_md(text):
    text = re.sub(r"[`*_#>|]", " ", str(text or ""))
    text = text.replace("✅", " ").replace("🔴", " ").replace("🟠", " ")
    return " ".join(text.split())


def parse_claims(path):
    """从 BOARD.md 的「claim 分布」表解析全部状态档 + total。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    started = False
    rows = {}
    for line in lines:
        s = line.strip()
        if not started:
            if s.startswith("###") and "claim" in s.lower() and "分布" in s:
                started = True
            continue
        if not s.startswith("|"):
            if rows:
                break
            continue
        cells = [strip_md(c).strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        state = cells[0].lower()
        if not state or state in ("状态", "state", "---"):
            continue
        if not cells[1].isdigit():
            continue
        rows[state] = int(cells[1])
    if not rows:
        return None
    return {
        "total": sum(rows.values()),
        "verified": rows.get("verified", 0),
        "refuted": rows.get("refuted", 0),
        "contested": rows.get("contested", 0),
        "method": rows.get("method", 0),
        "hypothesis": rows.get("hypothesis", 0),
        "parked": rows.get("parked", 0),
    }


def parse_board_tasks(path):
    """解析 BOARD.md 任务表行：{task_id: [行文本...]}（只保留 BOARD_IDS）。"""
    out = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return out
    pat = re.compile(r"^\|\s*`(r[A-Za-z0-9]{5})`")
    for line in lines:
        s = line.strip()
        m = pat.match(s)
        if not m:
            continue
        tid = m.group(1)
        if tid not in BOARD_IDS:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        text = cells[-1] if cells else ""
        if text:
            out.setdefault(tid, []).append(text)
    return out


def mtime_epoch(path):
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return None


def parse_local_time(text):
    """'2026-10-21 13:05:11'（本机时区）-> epoch 秒。"""
    try:
        import datetime
        return int(datetime.datetime.strptime(str(text), "%Y-%m-%d %H:%M:%S").timestamp())
    except (TypeError, ValueError, OSError):
        return None


def collect_tokens(home):
    """累加 cwd == CWD_FILTER 的 session token / stats 用量。"""
    out = {
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
    errors = 0
    d = os.path.join(home, ".dsh", "storages", "session_projcache", "sessions")
    try:
        files = glob.glob(os.path.join(d, "*.json"))
    except OSError:
        return out, 1
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            errors += 1
            continue
        rec = doc.get("record") or {}
        ident = rec.get("identity") or {}
        if ident.get("cwd") != CWD_FILTER:
            continue
        rows = rec.get("rows") or {}
        tu = ((rows.get("tokenUsage") or {}).get("val") or {}).get("totals") or {}
        ss = (rows.get("sessionStats") or {}).get("val") or {}
        out["sessions"] += 1
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
                out[key] += int(val or 0)
            except (TypeError, ValueError):
                pass
    return out, errors


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def payload_u1(home):
    u1dir = os.path.join(home, "taolunchaijie", "u1")
    data = {
        "checked": None, "matched": None, "mismatch": None,
        "generated_at": None, "gen_epoch": None, "mtime": None,
        "symbols": None, "du_kb": None,
        "full_manifest_at": None, "full_manifest_epoch": None,
        "fapi_at": None, "fapi_epoch": None, "fapi_symbols": None, "fapi_elapsed_s": None,
    }
    vr = os.path.join(u1dir, "verify_report.json")
    doc = read_json(vr)
    if isinstance(doc, dict):
        summary = doc.get("summary") or {}
        data["checked"] = summary.get("checked")
        data["matched"] = summary.get("matched")
        data["mismatch"] = summary.get("mismatch")
        data["generated_at"] = doc.get("generated_at")
        data["gen_epoch"] = parse_local_time(doc.get("generated_at"))
    data["mtime"] = mtime_epoch(vr)

    r = run(["du", "-sk", u1dir], timeout=10)
    if r["rc"] == 0 and r["out"]:
        try:
            data["du_kb"] = int(r["out"].split()[0])
        except (IndexError, ValueError):
            data["du_kb"] = None

    fm = read_json(os.path.join(u1dir, "full", "fetch_manifest.json"))
    if isinstance(fm, dict):
        data["full_manifest_at"] = fm.get("generated_at")
        data["full_manifest_epoch"] = parse_local_time(fm.get("generated_at"))
        sym = fm.get("symbols")
        if isinstance(sym, list):
            data["symbols"] = len(sym)
        elif isinstance(sym, int):
            data["symbols"] = sym
    if data["symbols"] is None:
        try:
            with open(os.path.join(u1dir, "symbols_524.txt"), "r", encoding="utf-8", errors="replace") as fh:
                data["symbols"] = len([ln for ln in fh.read().splitlines() if ln.strip()])
        except OSError:
            pass

    fapi = read_json(os.path.join(u1dir, "fapi", "manifest_metrics.json"))
    if isinstance(fapi, dict):
        data["fapi_at"] = fapi.get("generated_at")
        data["fapi_epoch"] = parse_local_time(fapi.get("generated_at"))
        data["fapi_elapsed_s"] = fapi.get("elapsed_s")
        sym = fapi.get("symbols")
        if isinstance(sym, list):
            data["fapi_symbols"] = len(sym)
        elif isinstance(sym, int):
            data["fapi_symbols"] = sym
    return data


def main():
    home = os.path.expanduser("~")
    repo = os.path.join(home, "crypto-agent")
    now = int(time.time())
    payload = {
        "host": run(["hostname"])["out"],
        "now": now,
    }

    git = {"head": None, "commit_ct": None, "dirty": None, "error": None, "log": []}
    if os.path.isdir(os.path.join(repo, ".git")):
        r = run(["git", "-C", repo, "rev-parse", "--short", "HEAD"])
        if r["rc"] == 0 and r["out"]:
            git["head"] = r["out"].splitlines()[0]
        else:
            git["error"] = r["err"] or ("git rev-parse rc=%s" % r["rc"])
        r = run(["git", "-C", repo, "log", "-1", "--format=%ct"])
        if r["rc"] == 0 and r["out"]:
            try:
                git["commit_ct"] = int(r["out"].splitlines()[0])
            except (TypeError, ValueError):
                pass
        r = run(["git", "-C", repo, "status", "--porcelain"])
        if r["rc"] == 0:
            git["dirty"] = len([ln for ln in r["out"].splitlines() if ln.strip()])
        r = run(["git", "-C", repo, "log", "-6", "--format=%h|%ct|%s"])
        if r["rc"] == 0:
            for line in r["out"].splitlines():
                parts = line.split("|", 2)
                if len(parts) != 3:
                    continue
                try:
                    ct = int(parts[1])
                except ValueError:
                    continue
                git["log"].append({"h": parts[0], "ct": ct, "subject": parts[2][:120]})
    else:
        git["error"] = "repo missing: " + repo
    payload["git"] = git

    board = os.path.join(repo, "BOARD.md")
    payload["claims"] = parse_claims(board)
    payload["board_tasks"] = parse_board_tasks(board)
    payload["board_mtime"] = mtime_epoch(board)

    payload["u1"] = payload_u1(home)

    tokens, token_errors = collect_tokens(home)
    payload["tokens"] = tokens
    payload["token_errors"] = token_errors

    r = run(["pgrep", "-f", "DeepSeek Harness"])
    pid_lines = [ln for ln in r["out"].splitlines() if ln.strip()]
    payload["dsh"] = {"running": bool(r["rc"] == 0 and pid_lines), "count": len(pid_lines)}

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
