"""material_trend_refresh.py — 主力合约历史 → 材料 trend 字段自动刷新

用 akshare 主力连续行情(futures_main_sina) 计算 20/60 日涨跌,
更新 config/material_discoveries_auto.yaml 候选中与期货品种对应的 trend。

用法:
  python -m etf_platform.scripts.material_trend_refresh [--apply]

  --apply  写回候选文件的 trend 字段 (current 不动)
  不带    只预览计算出的趋势

依赖: ① 先跑 material_auto_discover 生成候选文件。
"""
import sys
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform/
CANDIDATE_FILE = BASE / "config" / "material_discoveries_auto.yaml"

# 候选材料名 → 新浪主力连续 symbol (部分; 无映射的跳过)
SYMBOL_MAP = {
    "焦煤": "JM0", "铁矿石": "I0", "氧化铝": "AO0", "工业硅": "SI0",
    "纯碱": "SA0", "烧碱": "SH0", "纸浆": "SP0", "苯乙烯": "EB0",
    "乙二醇": "EG0", "聚丙烯": "PP0", "短纤": "PF0", "对二甲苯": "PX0",
    "丙烯": "PP0", "液化石油气": "PG0", "低硫燃料油": "LU0", "燃油": "FU0",
    "合成橡胶": "BR0", "20号胶": "NR0", "热卷": "HC0", "线材": "WR0",
    "锰硅": "SM0", "钯": "PA0", "铂": "PL0", "油菜籽": "RS0",
    "菜籽油": "OI0", "菜籽粕": "RM0", "豆一": "A0", "豆二": "B0",
    "豆油": "Y0", "花生": "PK0", "苹果": "AP0", "红枣": "CJ0",
    "鸡蛋": "JD0", "粳米": "RR0", "原木": "LG0", "棉纱": "CY0",
}


def calc_trend(symbol: str, days: int = 60) -> str | None:
    """主力连续 60 日涨跌 → 趋势描述. 数据不足返回 None."""
    try:
        import akshare as ak
        from ..utils.thread_timeout import run_with_timeout
        df = run_with_timeout(ak.futures_main_sina, symbol=symbol, timeout=30)
        if df is None or len(df) < 20:
            return None
        closes = df["收盘价"].astype(float)
        recent = closes.tail(days)
        start = recent.iloc[0]
        end = recent.iloc[-1]
        if start <= 0:
            return None
        pct = (end / start - 1) * 100
        if pct > 5:
            return f"↑ {pct:.0f}% ({days}日, 主力连续)"
        elif pct < -5:
            return f"↓ {abs(pct):.0f}% ({days}日, 主力连续)"
        else:
            return f"→ {pct:+.1f}% ({days}日, 主力连续)"
    except Exception:
        return None


def main():
    apply = "--apply" in sys.argv
    if not CANDIDATE_FILE.exists():
        print(f"候选文件不存在: {CANDIDATE_FILE}\n先运行 material_auto_discover --apply")
        return

    with open(CANDIDATE_FILE, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}
    mats = payload.get("materials", {})

    updated = 0
    for name, mat in mats.items():
        symbol = SYMBOL_MAP.get(name)
        if not symbol:
            continue
        trend = calc_trend(symbol)
        if trend:
            print(f"  {name:8s} {symbol:5s} -> {trend}")
            if apply:
                mat["trend"] = trend
                updated += 1

    if apply and updated:
        with open(CANDIDATE_FILE, "w", encoding="utf-8") as f:
            yaml.dump(payload, f, allow_unicode=True, sort_keys=False)
        print(f"\n已更新 {updated} 个候选的 trend 字段")
    else:
        print(f"\n(预览 {updated} 个 — 加 --apply 写回)")


if __name__ == "__main__":
    main()
