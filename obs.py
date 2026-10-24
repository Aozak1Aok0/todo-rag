r"""最小可观测：事件日志与汇总。

只记"事后有用"的字段：谁、多慢、多少 token、花了多少、成功与否。
不记 key、不记完整答案（避免日志变成新的泄露面）。

事件文件：logs/events-YYYYMMDD.jsonl（每天一个文件）
汇总入口：main.py 的 GET /stats
"""

import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = Path(os.getenv("OBS_DIR", str(BASE_DIR / "logs")))

# 单价：美元 / 每百万 token。默认按 DeepSeek 公开价（2025），可用环境变量覆盖。
RATE_IN = float(os.getenv("DEEPSEEK_PRICE_IN", "0.27"))
RATE_OUT = float(os.getenv("DEEPSEEK_PRICE_OUT", "1.10"))


def _file_for(d: date) -> Path:
    return LOG_DIR / f"events-{d.strftime('%Y%m%d')}.jsonl"


def estimate_cost(tokens_in: int = 0, tokens_out: int = 0) -> float:
    return round(tokens_in / 1e6 * RATE_IN + tokens_out / 1e6 * RATE_OUT, 6)


def log_event(kind: str, name: str, ok: bool = True, latency_ms: int | None = None,
              tokens_in: int = 0, tokens_out: int = 0, error: str | None = None,
              **meta) -> dict:
    """写一行事件。永远不抛异常 —— 观测不能拖垮主流程。"""
    event = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,                 # rag / agent / tool / eval ...
        "name": name,                 # POST /rag / mcp.search_docs ...
        "ok": bool(ok),
        "latency_ms": latency_ms,
        "tokens_in": int(tokens_in or 0),
        "tokens_out": int(tokens_out or 0),
        "cost_usd": estimate_cost(tokens_in or 0, tokens_out or 0),
        "error": error,
    }
    if meta:
        event["meta"] = meta
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_file_for(date.today()), "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass
    return event


def _p95(values):
    if not values:
        return 0
    s = sorted(values)
    return s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]


def summarize(days: int = 7) -> dict:
    """按 (kind, name) 聚合最近 N 天。返回 {"totals": ..., "groups": [...]}"""
    days = max(1, min(int(days), 90))
    today = date.today()
    rows = []
    for offset in range(days):
        p = _file_for(today - timedelta(days=offset))
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    def blank():
        return {"count": 0, "errors": 0, "latency": [], "tokens_in": 0,
                "tokens_out": 0, "cost_usd": 0.0}

    groups = {}
    totals = blank()
    for r in rows:
        key = (r.get("kind", "?"), r.get("name", "?"))
        g = groups.setdefault(key, blank())
        for target in (g, totals):
            target["count"] += 1
            target["errors"] += 0 if r.get("ok") else 1
            if r.get("latency_ms") is not None:
                target["latency"].append(r["latency_ms"])
            target["tokens_in"] += r.get("tokens_in") or 0
            target["tokens_out"] += r.get("tokens_out") or 0
            target["cost_usd"] += r.get("cost_usd") or 0.0

    def finish(x):
        lat = x.pop("latency")
        out = dict(x)
        out["avg_latency_ms"] = round(sum(lat) / len(lat)) if lat else 0
        out["p95_latency_ms"] = _p95(lat)
        out["cost_usd"] = round(out["cost_usd"], 6)
        out["error_rate"] = round(out["errors"] / out["count"], 3) if out["count"] else 0.0
        return out

    return {
        "window_days": days,
        "rates_usd_per_m": {"in": RATE_IN, "out": RATE_OUT},
        "totals": finish(totals),
        "groups": [
            {"kind": k, "name": n, **finish(v)}
            for (k, n), v in sorted(groups.items(), key=lambda kv: -kv[1]["count"])
        ],
    }