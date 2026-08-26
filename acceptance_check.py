# -*- coding: utf-8 -*-
"""acceptance_check.py — 每日产物自动验收（G4 闭环）

cron 心跳(etf_heartbeat_latest.json)只记录运行不做验收断言，陈旧产物
(如 screener_top20.json 停在 07-14)无人报警。本模块在每日 patrol 尾部做断言：
今日有推荐 / 核心产物 mtime<24h / 心跳<48h / stale 标记机制在位。
fail 写告警字段供飞书日报呈现。单检查内部异常 → 该项 fail 且 detail 含异常类型。
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
ARTIFACTS = ("price_cache.json", "kline_trend_cache.json", "news_etf_signals.json")
HEARTBEAT = "etf_heartbeat_latest.json"
RECOMMENDATIONS = "recommendations_log.jsonl"
FRESH_24H = timedelta(hours=24)
HEARTBEAT_TTL = timedelta(hours=48)


def _fmt_age(age: timedelta) -> str:
    hours = age.total_seconds() / 3600.0
    return f"{hours:.1f}h"


def _check_recommendations(data_dir: Path, today: datetime) -> dict:
    log = data_dir / RECOMMENDATIONS
    if not log.exists():
        return {"ok": False, "detail": f"缺失 {RECOMMENDATIONS}"}
    date_s = today.strftime("%Y-%m-%d")
    with open(log, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if rec.get("date") == date_s:
                return {"ok": True, "detail": f"今日({date_s})有推荐"}
    return {"ok": False, "detail": f"今日({date_s})无推荐记录"}


def _check_artifacts(data_dir: Path, now: datetime) -> dict:
    stale = []
    for name in ARTIFACTS:
        p = data_dir / name
        if not p.exists():
            stale.append(f"{name}(缺失)")
            continue
        age = now - datetime.fromtimestamp(p.stat().st_mtime)
        if age > FRESH_24H:
            stale.append(f"{name}(mtime {_fmt_age(age)})")
    if stale:
        return {"ok": False, "detail": "陈旧产物: " + "; ".join(stale)}
    return {"ok": True, "detail": "三个核心产物 mtime<24h"}


def _check_heartbeat(data_dir: Path, now: datetime) -> dict:
    hb = data_dir / HEARTBEAT
    if not hb.exists():
        return {"ok": False, "detail": f"缺失 {HEARTBEAT}"}
    age = now - datetime.fromtimestamp(hb.stat().st_mtime)
    if age > HEARTBEAT_TTL:
        return {"ok": False, "detail": f"心跳超龄({_fmt_age(age)}>48h)"}
    return {"ok": True, "detail": f"心跳 mtime<48h ({_fmt_age(age)})"}


def _check_stale_mechanism() -> dict:
    try:
        from etf_platform.analysis.material_bridge import material_freshness_report
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {str(e)[:120]}"}
    try:
        report = material_freshness_report()
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {str(e)[:120]}"}
    if isinstance(report, dict):
        return {"ok": True, "detail": f"机制在位(material_freshness_report 返回 dict)"}
    return {"ok": False, "detail": f"material_freshness_report 返回非 dict: {type(report).__name__}"}


def validate_daily_outputs(base_dir=None, now=None) -> dict:
    """验收今日输出产物。

    base_dir 缺省=脚本所在目录(仓库根)；now 可注入固定时间保证测试确定性。
    返回 {"checked_at": iso, "all_ok": bool, "checks": [{"name","ok","detail"}...]}。
    """
    base = Path(base_dir) if base_dir else BASE
    data_dir = base / "data"
    now = now or datetime.now()

    checks = []
    for name, fn in (
        ("recommendations_today", lambda: _check_recommendations(data_dir, now)),
        ("artifacts_fresh_24h", lambda: _check_artifacts(data_dir, now)),
        ("heartbeat_alive", lambda: _check_heartbeat(data_dir, now)),
        ("stale_mechanism_armed", _check_stale_mechanism),
    ):
        try:
            result = fn()
            ok = bool(result["ok"])
            detail = str(result.get("detail", ""))
        except Exception as e:  # loud failure，不静默
            ok = False
            detail = f"{type(e).__name__}: {str(e)[:120]}"
        checks.append({"name": name, "ok": ok, "detail": detail})

    return {
        "checked_at": now.isoformat(),
        "all_ok": all(c["ok"] for c in checks),
        "checks": checks,
    }
