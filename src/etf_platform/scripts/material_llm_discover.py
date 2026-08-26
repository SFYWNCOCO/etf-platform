"""material_llm_discover.py — LLM 驱动的未知新材料发现

流水线:
  1. 拉取多源新闻标题流 (华尔街见闻/36氪/微博等, 全量不过滤)
  2. 与现有材料库去重 (已知材料标题跳过, 省 token)
  3. 批量标题 → LLM (agnes→deepseek→规则回退) → 提取候选新材料
  4. 候选写入 config/material_llm_discoveries.yaml (待人工确认)

用法:
  python -m etf_platform.scripts.material_llm_discover [--limit=60] [--apply]

  --limit=N   最多分析的新闻条数 (默认 60, 控 LLM 成本)
  --apply     写入候选文件; 不带只打印
"""
import json
import re
import sys
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform/
OUT_FILE = BASE / "config" / "material_llm_discoveries.yaml"

# 非材料类标题关键词 (金融/宏观/无关, 直接跳过)
_IRRELEVANT = [
    "股市", "大盘", "涨停", "跌停", "A股", "港股", "美股", "指数", "基金",
    "央行", "美联储", "利率", "汇率", "GDP", "CPI", "PMI", "财报", "营收",
    "房价", "楼市", "保险", "银行", "券商", "IPO", "减持", "回购",
]


def fetch_news_titles(limit: int):
    """多源拉取新闻标题 (全量, 不过滤)."""
    titles = []
    seen = set()
    sources = [
        ("wallstreetcn", "https://api-one.wallstcn.com/apiv1/content/information-flow?channel=global-channel&accept=article&limit=30",
         "data.items[].resource.title"),
    ]
    try:
        import urllib.request
        req = urllib.request.Request(sources[0][1], headers={"User-Agent": "Mozilla/5.0", "Referer": "https://wallstreetcn.com/"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("data", {}).get("items", []):
            res = item.get("resource") or {}
            t = str(res.get("title") or res.get("content_short") or "").strip()
            if t and t not in seen:
                seen.add(t)
                titles.append(t)
    except Exception as e:
        print(f"  [WARN] wallstreetcn fetch failed: {e}", file=sys.stderr)
    # 36kr 快讯
    try:
        from bs4 import BeautifulSoup
        import urllib.request
        req = urllib.request.Request("https://36kr.com/newsflashes", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        for el in soup.select(".newsflash-item, .item-title, h2, h3")[:80]:
            t = el.get_text(strip=True)
            if t and 6 < len(t) < 60 and t not in seen:
                seen.add(t)
                titles.append(t)
    except Exception as e:
        print(f"  [WARN] 36kr fetch failed: {e}", file=sys.stderr)
    return titles[:limit]


def is_relevant(title: str, existing: set) -> bool:
    """标题是否可能涉及新材料 (去重已知 + 去无关)."""
    if any(k in title for k in _IRRELEVANT):
        return False
    for name in existing:
        if name and len(name) >= 2 and (name in title or title in name):
            return False  # 已知材料, 跳过
    return True


def llm_extract_materials(titles: list[str]) -> list[dict]:
    """LLM 从新闻标题中提取新材料候选."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"))
    try:
        import llm_config
        from llm_extractor import _call_llm
    except ImportError as e:
        print(f"  [WARN] LLM 基建不可用: {e}, 回退规则提取", file=sys.stderr)
        return _rule_extract(titles)

    cfg = llm_config.load_llm_config()
    prompt = (
        "你是材料领域分析师。从以下财经新闻标题中, 提取**可能的新兴/关键材料**。\n"
        "规则:\n"
        "1. 只提取具体材料实体 (如 '固态电解质'、'碳化硅'、'钕铁硼'、'钙钛矿'), 不是公司/行业/宏观\n"
        "2. 排除金融/宏观/公司事件\n"
        "3. 每条新闻最多 1 个材料, 没有则跳过\n"
        "4. 输出 JSON 数组: [{\"material\": \"材料名\", \"news\": \"原文标题\", \"why\": \"为什么重要\"}]\n\n"
        f"新闻标题:\n" + "\n".join(f"- {t}" for t in titles)
    )
    for provider in ("agnes", "deepseek"):
        pc = cfg.get(provider, {})
        if not pc.get("api_key"):
            continue
        try:
            print(f"  调用 LLM ({provider}) ...")
            result = _call_llm(prompt, pc)
            return _parse_llm_json(result)
        except Exception as e:
            print(f"  [WARN] {provider} failed: {e}", file=sys.stderr)
    return _rule_extract(titles)


def _parse_llm_json(result) -> list[dict]:
    """_call_llm 返回已 json.loads 的 dict(可能是 list/含内容的 dict), 容错解析."""
    if isinstance(result, list):
        return [d for d in result if isinstance(d, dict) and d.get("material")]
    if isinstance(result, dict):
        for key in ("materials", "data", "result", "output", "content"):
            v = result.get(key)
            if isinstance(v, list):
                return [d for d in v if isinstance(d, dict) and d.get("material")]
        text = json.dumps(result, ensure_ascii=False)
    else:
        text = str(result)
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
        return [d for d in data if isinstance(d, dict) and d.get("material")]
    except (json.JSONDecodeError, ValueError):
        out = []
        for line in text.splitlines():
            mm = re.search(r'"material"\s*:\s*"([^"]+)"', line)
            if mm:
                out.append({"material": mm.group(1), "news": "", "why": ""})
        return out


def _rule_extract(titles: list[str]) -> list[dict]:
    """无 LLM 时的规则回退: 从标题提取 'XX材料/XX电池/XX芯片' 等模式."""
    out = []
    for t in titles:
        for pat in (r"([\u4e00-\u9fa5A-Za-z0-9]{2,10}(?:材料|电池|芯片|半导体|合金|膜|纤维|催化剂))",):
            m = re.search(pat, t)
            if m:
                out.append({"material": m.group(1), "news": t, "why": "规则提取"})
    return out


def main():
    args = [a for a in sys.argv[1:]]
    limit = 60
    for a in args:
        if a.startswith("--limit="):
            limit = int(a.split("=")[1])
    apply = "--apply" in args

    print("① 拉取新闻 ...")
    titles = fetch_news_titles(limit)
    print(f"   获取 {len(titles)} 条标题")

    from etf_platform.analysis.material_bridge import _get_material_signals
    existing = set(_get_material_signals().keys())
    candidates_in = [t for t in titles if is_relevant(t, existing)]
    print(f"   去重后剩 {len(candidates_in)} 条待分析 (已知 {len(titles) - len(candidates_in)} 条跳过)")

    if not candidates_in:
        print("   无相关新闻")
        return

    print("② LLM 提取新材料 ...")
    found = llm_extract_materials(candidates_in)
    found = [f for f in found if f["material"] not in existing]

    # 规则回退产物质量低(可能提取出非材料词), 只预览不写入, 防止噪声入库
    used_rule_fallback = any(f.get("why") == "规则提取" for f in found)
    if used_rule_fallback:
        print(f"   警告: LLM 不可用, 规则回退提取 {len(found)} 个(质量低, 不写入)")
        for f in found:
            print(f"  ⚠️ {f['material']:20s} <- {f['news'][:40]}")
        return
    print(f"   提取 {len(found)} 个新材料候选")

    for f in found:
        print(f"  🆕 {f['material']:20s} <- {f['news'][:40]}")
        if f.get("why"):
            print(f"      {f['why'][:60]}")

    if found and apply:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {"materials": {f["material"]: {
            "current": "待补充", "trend": "→ 待确认",
            "warning": f"🆕 LLM 新闻发现: {f.get('why', '')[:60]}",
            "affects": [], "note": f"来源新闻: {f.get('news', '')[:80]}"
        } for f in found}}
        with open(OUT_FILE, "w", encoding="utf-8") as fp:
            yaml.dump(payload, fp, allow_unicode=True, sort_keys=False)
        print(f"\n已写入 {OUT_FILE} ({len(found)} 个候选)")
    elif found:
        print("\n(未写入 — 加 --apply 生成候选文件)")


if __name__ == "__main__":
    main()
