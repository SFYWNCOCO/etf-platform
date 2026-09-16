"""material_auto_discover.py — 期货品种 → 新材料候选自动发现

从 akshare 全市场期货合约表(828个合约)提取品种清单, 与现有材料库比对,
输出未覆盖的品种为"待确认候选"到 config/material_discoveries_auto.yaml。

用法:
  python -m etf_platform.scripts.material_auto_discover [--apply]

  --apply  把候选写入 material_quick_add.yaml (仍为注释状态, 需人工取消注释激活)
  不带    只输出候选清单预览, 不写文件

设计: 增量不替换 — 候选只包含"库中没有的"品种; affects 留空, 由人工或后续规则填充。
"""
import re
import sys
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform/
CANDIDATE_FILE = BASE / "config" / "material_discoveries_auto.yaml"


# 非材料类品种黑名单 (金融/指数/杂项, 不是实体材料)
_NON_MATERIAL = {
    "10年国债", "2年期国债", "30年期国债", "5年期国债", "上证50指数",
    "中证股指", "深指数", "集运指数", "瓶片PR", "聚丙烯月均价",
    "聚乙烯月均价", "聚氯乙烯月均价", "铸造铝", "胶板", "国际铜",
}


def fetch_futures_products():
    """拉取全市场期货合约, 按品种去重."""
    import akshare as ak
    from ..utils.thread_timeout import run_with_timeout
    df = run_with_timeout(ak.futures_comm_info, timeout=30)
    if df is None or df.empty:
        return []
    products = set()
    for raw in df["合约名称"].astype(str):
        name = re.sub(r"\d{3,4}", "", raw).strip()  # 去合约月份 "黄金2608"→"黄金"
        name = re.sub(r"^(沪|连|郑|INE)?", "", name)  # 去交易所前缀 "沪铜"→"铜"
        if name and len(name) <= 8 and name not in _NON_MATERIAL:
            products.add(name)
    return sorted(products)


def load_existing_names():
    """现有材料库名称 + 关键 ETF sector 名 (用于模糊匹配)."""
    from etf_platform.analysis.material_bridge import _get_material_signals
    return set(_get_material_signals().keys())


def match_score(product: str, existing: set) -> bool:
    """匹配规则: 材料名包含品种词 或 品种词是材料名子串 (长度>=2 防误匹配)."""
    if len(product) < 2 and product not in "金银铜铝锌镍铅锡":
        return False
    for name in existing:
        if product in name or name in product:
            return True
    return False


def main():
    apply = "--apply" in sys.argv
    print("拉取期货全品种 ...")
    products = fetch_futures_products()
    print(f"期货品种(去重后): {len(products)} 个")

    existing = load_existing_names()
    print(f"现有材料库: {len(existing)} 种")

    missing = [p for p in products if not match_score(p, existing)]
    print(f"\n未覆盖候选: {len(missing)} 个")
    for p in missing:
        print(f"  🆕 {p}")

    if not missing:
        print("\n✅ 期货品种已全部覆盖, 无需新增")
        return

    if apply:
        CANDIDATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "materials": {
                p: {"current": "待补充", "trend": "→ 待确认",
                    "warning": "🆕 期货品种自动发现, 待确认 affects 映射",
                    "affects": []}
                for p in missing
            }
        }
        with open(CANDIDATE_FILE, "w", encoding="utf-8") as f:
            yaml.dump(payload, f, allow_unicode=True, sort_keys=False)
        print(f"\n已写入 {CANDIDATE_FILE}")
        print("下一步: 为候选补充 affects 后, 移入 material_quick_add.yaml 激活")
    else:
        print(f"\n(未写入 — 加 --apply 生成候选文件)")


if __name__ == "__main__":
    main()
