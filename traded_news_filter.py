#!/usr/bin/env python3
"""traded_news_filter.py — 可交易新闻过滤（规则引擎，不调 LLM，无网络）。

背景（KB d751）: news_raw_sources.json 的 87 条新闻全部进 judge_direction() 生成
sector 信号，含"天齐锂业遭摩根大通减持"这类个股日常公告——与行业 ETF 交易无关的
噪音。本模块在 auto_sentiment 的 sector 匹配+方向判定前加"可交易性门禁"。

判定层级（克制，只覆盖规格列出的噪音模式）:
  1. 社会/娱乐/科普/天气灾害 → 直接拒（教程/频道页是 sear 来源实际噪音，规格"无关动态"扩展）
  2. 个股公告句式（增持减持/日常公告）→ 拒；仅当同时含宏观/政策/产业强词才翻案放行
     （公告句式里即使出现"锂/光模块"等字也是公司名一部分，不能按行业词翻案）
  3. 行业词（复用 auto_sentiment.SECTOR_KEYWORDS）/ 政策产业词 → 可交易
  4. 宏观信号 / 强信号事件(涨停/爆雷等，需有明确对象代码) → 可交易
  5. 其余 → 拒
"""
import re

from auto_sentiment import SECTOR_KEYWORDS, match_sector

# ── 个股公告噪音（增持减持 / 日常公告）──
_HOLDINGS_RE = re.compile(r"减持|增持|买入评级|卖出评级|持股比例")
_DAILY_RE = re.compile(
    r"停牌|复牌|分红|除权|除息|股东大会|股东会|董事会|监事会|年报|季报|业绩快报|"
    r"回购|股权激励|股票激励|上市公告书|法律意见书|保荐书|募集说明书|审计报告|"
    r"财务报告|核查意见|问询函|配股|回售|澄清公告|现金管理|承诺函|募集资金|"
    r"计提|减值|诉讼|离任|更名|发行股票|定增"
)

# ── 社会/娱乐/体育/天气灾害/地缘冲突/人事任命 → 直接拒 ──
_SOCIAL_RE = re.compile(
    r"娱乐|综艺|明星|八卦|体育|赛事|比分|娱乐圈|电影|剧集|收视率|"
    r"气温|山火|火灾|洪水|台风|地震|暴雨|谣言|"
    r"空难|相撞|出任|俄军|乌军|顿涅茨克"
)

# ── 教程/科普/频道页（sear 来源常见噪音）──
_TUTORIAL_RE = re.compile(r"教程|入门|百科|菜鸟|FAQ|是什么|什么是|What is|频道|栏目|书评|读书|CSDN")

# ── 翻案强词：公告句式命中后，仅当含这些词才视为真产业/宏观新闻 ──
_INDUSTRY_STRONG_RE = re.compile(
    r"政策|规划|补贴|招标|中标|扩产|涨价|降价|新规|国产替代|产业链|"
    r"出口|进口|关税|反倾销|景气|产能"
)
_MACRO_RE = re.compile(r"央行|降准|降息|利率|CPI|PPI|GDP|PMI|社融|M2|美联储|加息|缩表|通胀|通缩|非农|美债|国债|收益率|汇率")

# ── 强信号事件：需有明确对象（6 位代码）才可交易 ──
_STRONG_EVENT_RE = re.compile(r"涨停|跌停|暴涨|暴跌|崩盘|爆雷|违约|退市")
_CODE_RE = re.compile(r"\d{6}")

# ── 异常/拐点信号（d807 发现能力落地：多年首次/历史新高/停工重启是拐点）──
_ANOMALY_PATTERNS = [
    ("首次型", re.compile(r"多年首次|历史首次|史上首次|首次突破|首次超过|首次超越|首次实现|首次.{0,8}(突破|超过|达成|跨越)")),
    ("纪录型", re.compile(r"历史新高|历史新低|创纪录|破纪录")),
    ("重启型", re.compile(r"停工.{0,12}重启|重启.{0,12}(工厂|产线|建设|项目)")),
    ("拐点型", re.compile(r"里程碑|拐点")),
]


def detect_anomaly(text: str) -> list:
    """检测新闻中的异常/拐点信号（多年首次/历史新高/停工重启等）。

    Returns:
        命中的异常类型列表，如 ['纪录型', '重启型']；无命中返回 []
    """
    if not text:
        return []
    return [name for name, pat in _ANOMALY_PATTERNS if pat.search(text)]


def is_tradable(item: dict) -> tuple:
    """判断单条新闻是否可交易（能产生行业 ETF 信号）。

    Args:
        item: news_raw_sources.json items 的单条 dict，
            字段: source/lid/channel/title/time/url/summary/is_bearish

    Returns:
        (True, "reason") 可交易；reason 标注类型
        (False, "reason") 不可交易；reason 标注拒绝原因
    """
    text = " ".join(
        item.get(k) or "" for k in ("title", "summary", "url")
    )

    # 1) 社会/娱乐/科普/灾害 → 直接拒
    if _SOCIAL_RE.search(text):
        return False, "社会/娱乐/体育"
    if _TUTORIAL_RE.search(text):
        return False, "教程/科普/频道页"

    # 2) 个股公告句式 → 拒；含宏观/政策/产业强词才翻案
    holdings = _HOLDINGS_RE.search(text)
    daily = _DAILY_RE.search(text)
    if holdings or daily:
        if not (_MACRO_RE.search(text) or _INDUSTRY_STRONG_RE.search(text)):
            why = "增持减持公告" if holdings else "日常公告"
            return False, f"个股{why}"
        # 含翻案强词 → 继续按行业/宏观判定

    # 3) 异常/拐点信号（d807）→ 优先升级：命中 + 行业/宏观锚定即可交易并标记
    sectors = match_sector(text)
    anomalies = detect_anomaly(text)
    if anomalies and (sectors or _MACRO_RE.search(text)):
        return True, "异常信号:" + "/".join(anomalies)

    # 4) 行业词 / 政策产业词 → 可交易
    if sectors:
        return True, f"行业词:{sectors[0]}"
    if _INDUSTRY_STRONG_RE.search(text):
        return True, "政策/产业词"

    # 5) 宏观 / 强信号事件（有明确对象）→ 可交易
    if _MACRO_RE.search(text):
        return True, "宏观信号"
    if _STRONG_EVENT_RE.search(text) and _CODE_RE.search(text):
        return True, "强信号事件"

    # 6) 其余 → 拒
    return False, "无关动态/无行业词"


def filter_tradable(items: list) -> tuple:
    """过滤新闻列表，返回 (可交易列表, 不可交易列表)。"""
    tradable, noise = [], []
    for it in items:
        (tradable if is_tradable(it)[0] else noise).append(it)
    return tradable, noise
