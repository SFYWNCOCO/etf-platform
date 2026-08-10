"""prediction_monitor.py — 2周预测追踪与回测

每个交易日记录Top 3预测, 10个交易日后回测准确率。
"""
import json
import os
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent.parent  # decision/ -> etf_platform/ -> src/ -> etf-platform/
DATA_DIR = BASE / "data"
LOG_FILE = DATA_DIR / "two_week_predictions.jsonl"


def log_prediction(predictions: list, profile: str = "均衡"):
    """记录预测到JSONL日志
    
    Args:
        predictions: pick_top3返回的top3 list (3 items)
        profile: 风险偏好
    """
    DATE_DIR = DATA_DIR / "predictions"
    DATE_DIR.mkdir(parents=True, exist_ok=True)
    
    today = date.today().isoformat()
    record = {
        "date": today,
        "profile": profile,
        "timestamp": datetime.now().isoformat(),
        "top3": [
            {
                "code": p["code"],
                "name": p["name"],
                "sector": p.get("sector", ""),
                "two_week_score": p["two_week_score"],
                "pipeline_score": p.get("pipeline_score", 5.0),
                "z_composite": p.get("z_composite", 0),
                "trend_signal": p["trend_signal"],
                "change_20d": p["change_20d"],
                "change_10d": p.get("return_10d", 0),
            }
            for p in predictions[:3]
        ],
    }

    # Daily file
    daily_file = DATE_DIR / f"{today}.json"
    with open(daily_file, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    # Append to full log (幂等：同一天同 profile 去重，覆盖旧记录，防止 cron/手动
    # 重复触发导致回测样本被同一预测重复加权)
    lines = []
    if LOG_FILE.exists():
        with open(LOG_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if row.get("date") == today and row.get("profile") == profile:
                    continue  # 丢弃同日同 profile 旧记录
                lines.append(line)
    lines.append(json.dumps(record, ensure_ascii=False))
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return daily_file


def _return_since(pred_date_str: str, code: str, horizon: int = 10):
    """从预测日起 horizon 个交易日后的收益率（K线锚点法）。

    - 取预测日当天（或之后首个交易日）收盘价为 P0
    - 取 P0 之后第 horizon 个交易日收盘价为 P1
    - 返回 (P1-P0)/P0*100；数据不足或失败返回 None

    修复：旧逻辑用 get_trend 的"当前动量"（与预测日无关），导致命中率虚高。
    """
    from etf_platform.data.kline import _fetch_kline

    rows = _fetch_kline(code, days=80)  # 80 个日线 bar 足够覆盖预测日 + 2 周余量
    if not rows:
        return None
    start_idx = None
    for i, r in enumerate(rows):
        d = r.get("date") or r.get("day")
        if not d:
            continue
        if d >= pred_date_str:
            start_idx = i
            break
    if start_idx is None:
        return None
    p0 = float(rows[start_idx]["close"])
    if p0 <= 0:
        return None
    end_idx = min(start_idx + horizon, len(rows) - 1)
    p1 = float(rows[end_idx]["close"])
    if p1 <= 0:
        return None
    return (p1 - p0) / p0 * 100


def evaluate_prediction(days_back: int = 10):
    """回测历史预测: 检查预测日起 N 个交易日的涨跌幅（K线锚点法）

    Returns:
        dict with accuracy metrics
    """
    if not LOG_FILE.exists():
        return {"error": "No prediction history"}

    # Load all predictions
    predictions = []
    with open(LOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    predictions.append(json.loads(line))
                except Exception:
                    continue

    if not predictions:
        return {"error": "Empty prediction history"}

    results = []
    hits = 0
    total = 0
    return_avg = []

    for pred in predictions:
        pred_date = pred["date"]
        days_since = (date.today() - date.fromisoformat(pred_date)).days

        if days_since < 5:
            continue  # 还没足够时间验证

        total += 1
        for i, etf in enumerate(pred["top3"]):
            code = etf["code"]
            ret = _return_since(pred_date, code, days_back)
            if ret is None:
                continue
            return_avg.append(ret)

            hit = ret > 0
            if hit:
                hits += 1

            results.append({
                "date": pred_date,
                "code": code,
                "name": etf["name"],
                "rank": i + 1,
                "pred_score": etf["two_week_score"],
                "return_horizon": ret,
                "hit": hit,
            })

    if not results:
        return {"error": f"等待足够回测数据 (需>5天, 当前最早预测: {predictions[0]['date'] if predictions else 'N/A'})"}

    avg_return = sum(return_avg) / max(len(return_avg), 1)
    hit_rate = hits / max(len(results), 1) * 100

    return {
        "total_predictions": len(results),
        "hits": hits,
        "hit_rate": round(hit_rate, 1),
        "avg_return_10d": round(avg_return, 2),
        "details": sorted(results, key=lambda x: -x["pred_score"])[:10],
    }


def status_report() -> str:
    """生成监控状态报告"""
    hist_file = DATA_DIR / "predictions"
    if not hist_file.exists():
        return "暂无预测历史."
    
    # Only look for daily .json files, skip .jsonl log
    json_files = sorted([f for f in os.listdir(hist_file) if f.endswith('.json') and not f.endswith('.jsonl')])
    latest = json_files[-1] if json_files else None
    
    lines = ["📊 ETF 2周预测监控", f"={'='*50}"]
    
    if latest:
        with open(os.path.join(hist_file, latest), encoding="utf-8") as f:
            data = json.load(f)
        lines.append(f"\n最新预测: {data['date']} ({data['profile']}型)")
        for i, etf in enumerate(data["top3"], 1):
            lines.append(f"  {i}. {etf['code']} {etf['name']}")
            lines.append(f"     2周评分: {etf['two_week_score']}/100 | 穿透: {etf.get('pipeline_score', etf.get('composite_score', '?'))}")
            lines.append(f"     趋势: {etf.get('trend_signal','?')} 20日{etf.get('change_20d',0):+.1f}%")
    elif LOG_FILE.exists():
        # Fallback: read last line from JSONL
        with open(LOG_FILE, encoding="utf-8") as f:
            last_line = None
            for line in f:
                if line.strip():
                    last_line = line.strip()
        if last_line:
            data = json.loads(last_line)
            lines.append(f"\n最新预测(JSONL): {data['date']} ({data['profile']}型)")
            for i, etf in enumerate(data["top3"], 1):
                lines.append(f"  {i}. {etf['code']} {etf['name']}")
                lines.append(f"     2周评分: {etf['two_week_score']}/100 | 穿透: {etf.get('pipeline_score', etf.get('composite_score', '?'))}")
                lines.append(f"     趋势: {etf.get('trend_signal','?')} 20日{etf.get('change_20d',0):+.1f}%")
    
    # Evaluate
    eval_result = evaluate_prediction()
    if "hit_rate" in eval_result:
        lines.append(f"\n回测 ({eval_result['total_predictions']}次预测):")
        lines.append(f"  ✅ 命中率: {eval_result['hit_rate']}% ({eval_result['hits']}/{eval_result['total_predictions']})")
        lines.append(f"  📈 平均10日收益: {eval_result['avg_return_10d']:+.2f}%")
    else:
        lines.append(f"\n{eval_result.get('error', '')}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ETF 2周预测监控")
    parser.add_argument("--status", action="store_true", help="监控状态报告")
    parser.add_argument("--eval", type=int, default=10, help="回测天数")
    args = parser.parse_args()
    
    if args.status:
        print(status_report())
    else:
        print(evaluate_prediction(args.eval))
