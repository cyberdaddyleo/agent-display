#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agent-live/2 契约校验器（只读）。

用法：
    python live/validate_live.py                # 校验 ..\\live.json
    python live/validate_live.py <path>         # 校验指定文件

退出码：0 = PASS；1 = FAIL（并打印每一条不符项）。
"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PATH = BASE_DIR.parent / "live.json"

NODE_ORDER = ["win", "mac", "sg", "hk"]
AGENT_ORDER = ["collector", "aggregate", "futures", "agent-svc", "claims", "retrieval",
               "replay", "u1-vision", "u1-verify", "duckdb", "backup", "research"]
TOKEN_KEYS = ["inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens",
              "sessions", "turns", "steps", "decodeTokens", "llmMs"]
STATES = {"ok", "warn", "down", "unknown"}
ACTIVITY_STATES = {"done", "run", "warn"}
WHOS = {"WIN", "MAC", "SG", "HK"}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0]) if argv else DEFAULT_PATH
    errors = []

    def check(cond, message):
        if not cond:
            errors.append(message)

    try:
        with open(path, "r", encoding="utf-8") as fh:
            live = json.load(fh)
    except (OSError, ValueError) as exc:
        print("FAIL 无法读取/解析 %s: %s" % (path, exc))
        return 1

    check(isinstance(live, dict), "顶层不是 JSON 对象")
    if not isinstance(live, dict):
        print("FAIL " + "; ".join(errors))
        return 1

    for key in ("schema", "ts", "epoch", "collect", "nodes", "claims", "progress",
                "tokens", "metrics", "agents", "activity", "alerts"):
        check(key in live, "缺少顶层字段 %s" % key)
    check(live.get("schema") == "agent-live/2", "schema 应为 agent-live/2，实际 %r" % live.get("schema"))

    collect = live.get("collect") or {}
    check(isinstance(collect.get("ok"), bool), "collect.ok 应为 bool")
    check(isinstance(collect.get("took_ms"), int), "collect.took_ms 应为 int")
    check(isinstance(collect.get("errors"), list), "collect.errors 应为 list")

    nodes = live.get("nodes") or []
    check(isinstance(nodes, list) and len(nodes) == 4, "nodes 应为 4 条，实际 %s" % len(nodes))
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append("nodes[%d] 不是对象" % index)
            continue
        check(node.get("id") == NODE_ORDER[index], "nodes[%d].id 应为 %s" % (index, NODE_ORDER[index]))
        for key in ("label", "role", "state", "f1", "f2"):
            check(key in node, "nodes[%d] 缺少 %s" % (index, key))
        check(node.get("state") in STATES, "nodes[%d].state 非法 %r" % (index, node.get("state")))
        check(len(str(node.get("f1", ""))) <= 24, "nodes[%s].f1 超 24 字符" % node.get("id")) 
        check(len(str(node.get("f2", ""))) <= 24, "nodes[%s].f2 超 24 字符" % node.get("id"))

    claims = live.get("claims") or {}
    for key in ("total", "verified", "refuted", "contested", "method", "hypothesis", "parked"):
        check(key in claims, "claims 缺少 %s" % key)
    check(isinstance(claims.get("total"), int) and claims["total"] > 0, "claims.total 应为正整数")

    progress = live.get("progress") or {}
    for key in ("u1", "commit", "commit_at"):
        check(key in progress, "progress 缺少 %s" % key)

    tokens = live.get("tokens") or {}
    for part in ("win", "mac"):
        part_data = tokens.get(part) or {}
        for key in TOKEN_KEYS:
            check(key in part_data, "tokens.%s 缺少 %s" % (part, key))
    total = tokens.get("total") or {}
    for key in ("inputTokens", "outputTokens", "cacheReadTokens", "allTokens"):
        check(key in total, "tokens.total 缺少 %s" % key)
    try:
        expect_all = int(total.get("inputTokens", 0)) + int(total.get("outputTokens", 0)) + int(total.get("cacheReadTokens", 0))
        check(int(total.get("allTokens", -1)) == expect_all, "tokens.total.allTokens != 三项之和")
    except (TypeError, ValueError):
        errors.append("tokens.total 数值字段不是整数")
    win_total = sum(int((tokens.get("win") or {}).get(k) or 0)
                    for k in ("inputTokens", "outputTokens", "cacheReadTokens"))
    mac_total = sum(int((tokens.get("mac") or {}).get(k) or 0)
                    for k in ("inputTokens", "outputTokens", "cacheReadTokens"))
    check(win_total > 0, "tokens.win 三类 token 合计为 0（应真实非 0）")
    check(mac_total > 0, "tokens.mac 三类 token 合计为 0（应真实非 0）")

    metrics = live.get("metrics") or {}
    for key in ("bars", "u1", "sg", "hk", "win", "mac"):
        check(key in metrics, "metrics 缺少 %s" % key)
    bars = metrics.get("bars") or {}
    for key in ("m1", "m5", "m15", "h1"):
        check(key in bars, "metrics.bars 缺少 %s" % key)
        check(bars.get(key) is None or isinstance(bars.get(key), int), "metrics.bars.%s 应为 int|null" % key)
    u1 = metrics.get("u1") or {}
    for key in ("symbols", "size_mb", "checked", "matched", "at"):
        check(key in u1, "metrics.u1 缺少 %s" % key)
    sg = metrics.get("sg") or {}
    for key in ("data_lag_s", "htf15_lag_s", "futures_fresh", "data_fresh", "disk_free_g",
                "mem_free_g", "units_ok", "units_total"):
        check(key in sg, "metrics.sg 缺少 %s" % key)
    hk = metrics.get("hk") or {}
    for key in ("backup_mb", "age_s", "disk_free_g"):
        check(key in hk, "metrics.hk 缺少 %s" % key)
    win = metrics.get("win") or {}
    for key in ("raw_gb", "duckdb_gb", "u1_files", "fapi_files"):
        check(key in win, "metrics.win 缺少 %s" % key)
    mac = metrics.get("mac") or {}
    for key in ("head", "head_at", "dirty", "dsh"):
        check(key in mac, "metrics.mac 缺少 %s" % key)
    check(bars.get("m1") is not None, "metrics.bars.m1 为 null（SG COUNT 未取到）")

    agents = live.get("agents") or []
    check(isinstance(agents, list), "agents 应为 list")
    check(len(agents) == 12, "agents 应为 12 条，实际 %s" % len(agents))
    ids = [a.get("id") for a in agents if isinstance(a, dict)]
    check(ids == AGENT_ORDER, "agents 顺序/ID 不符：%s" % ids)
    for index, agent in enumerate(agents):
        if not isinstance(agent, dict):
            errors.append("agents[%d] 不是对象" % index)
            continue
        for key in ("id", "label", "zh", "where", "state", "pct", "note"):
            check(key in agent, "agents[%d] 缺少 %s" % (index, key))
        check(agent.get("state") in STATES, "agents[%s].state 非法 %r" % (agent.get("id"), agent.get("state")))
        check(agent.get("where") in ("WIN", "MAC", "SG", "HK"), "agents[%s].where 非法" % agent.get("id"))
        pct = agent.get("pct")
        check(isinstance(pct, int) and 0 <= pct <= 100, "agents[%s].pct 应为 0-100 整数" % agent.get("id"))
        check(len(str(agent.get("note", ""))) <= 24, "agents[%s].note 超 24 字符" % agent.get("id"))

    activity = live.get("activity") or []
    check(isinstance(activity, list), "activity 应为 list")
    check(12 <= len(activity) <= 16, "activity 应为 12-16 条，实际 %s" % len(activity))
    ages = []
    act_ids = set()
    for index, event in enumerate(activity):
        if not isinstance(event, dict):
            errors.append("activity[%d] 不是对象" % index)
            continue
        for key in ("id", "who", "title", "state", "age_s", "at"):
            check(key in event, "activity[%d] 缺少 %s" % (index, key))
        check(event.get("who") in WHOS, "activity[%s].who 非法 %r" % (event.get("id"), event.get("who")))
        check(event.get("state") in ACTIVITY_STATES, "activity[%s].state 非法 %r" % (event.get("id"), event.get("state")))
        at = str(event.get("at", ""))
        check(len(at) == 5 and at[2] == ":", "activity[%s].at 应为 HH:MM" % event.get("id"))
        if event.get("id") in act_ids:
            errors.append("activity id 重复：%s" % event.get("id"))
        act_ids.add(event.get("id"))
        ages.append(event.get("age_s"))
    clean_ages = [a for a in ages if isinstance(a, (int, float))]
    if len(clean_ages) == len(ages) and len(clean_ages) > 1:
        check(clean_ages == sorted(clean_ages), "activity 未按最新在前排序")

    alerts = live.get("alerts") or []
    check(isinstance(alerts, list), "alerts 应为 list")
    for alert in alerts:
        check(isinstance(alert, dict) and "level" in alert and "text" in alert,
              "alerts 条目应含 level/text")

    if errors:
        print("FAIL %s（%d 项）" % (path, len(errors)))
        for message in errors:
            print(" - " + message)
        return 1

    bars_text = "/".join("?" if bars.get(k) is None else str(bars[k]) for k in ("m1", "m5", "m15", "h1"))
    print("PASS %s" % path)
    print("  schema=%s ts=%s took=%sms ok=%s" % (
        live.get("schema"), live.get("ts"), collect.get("took_ms"), collect.get("ok")))
    print("  nodes=%s" % " ".join("%s:%s" % (n.get("id"), n.get("state")) for n in nodes))
    print("  claims total=%s verified=%s" % (claims.get("total"), claims.get("verified")))
    print("  tokens total all=%s win=%s mac=%s" % (
        total.get("allTokens"), win_total, mac_total))
    print("  bars m1/m5/m15/h1=%s u1=%s/%s symbols=%s" % (
        bars_text, u1.get("matched"), u1.get("checked"), u1.get("symbols")))
    print("  agents=%s" % " ".join("%s:%s/%s" % (a.get("id"), a.get("state"), a.get("pct")) for a in agents))
    print("  activity=%d alerts=%d" % (len(activity), len(alerts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
