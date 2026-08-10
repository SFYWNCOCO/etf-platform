#!/usr/bin/env python3
"""News Signal Extractor — 新闻信号提取模块

This module parses news articles and generates quantitative signals for ETF analysis.
It maps news content to sector-based keywords, computes sentiment scores, and outputs
structured signals compatible with the ETF pipeline framework.

Integration points:
- Consumes raw news from data/news_source.py
- Produces signals for L34_KBCatalyst layer and real-time enhancement modules
- Outputs JSON format consumable by pipeline._apply_kb_catalyst()
"""

from typing import Dict, List
from dataclasses import dataclass
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class NewsSignal:
    """单个新闻产生的ETF信号结构"""
    etf_code: str              # 关联的ETF代码
    sector: str                # 所属行业
    sentiment_score: float     # 情感分数 [-1, 1]，1=强烈正面，-1=强烈负面
    signal_strength: float     # 信号强度 [0, 1]，基于关键词匹配度
    keyword_matches: List[str] # 匹配到的关键词列表
    timestamp: str             # 时间戳
    source: str                # 新闻来源
    headline: str              # 新闻标题
    
    def as_dict(self) -> Dict:
        """转换为字典以便序列化"""
        return {
            "etf_code": self.etf_code,
            "sector": self.sector,
            "sentiment_score": round(self.sentiment_score, 4),
            "signal_strength": round(self.signal_strength, 4),
            "keyword_matches": self.keyword_matches,
            "timestamp": self.timestamp,
            "source": self.source,
            "headline": self.headline,
        }


class NewsSignalExtractor:
    """新闻信号提取器 — 核心处理逻辑"""
    
    def __init__(self):
        """初始化关键词映射和情感词典"""
        self.sector_keywords = self._load_sector_keywords()
        self.positive_words = self._load_positive_words()
        self.negative_words = self._load_negative_words()
        
    def _load_sector_keywords(self) -> Dict[str, List[str]]:
        """加载行业关键词映射（基于现有KB和行业分类）"""
        return {
            "半导体": ["半导体", "芯片", "硅", "晶圆", "制程", "光刻", 
                       "IC", "IC设计", "存储", "memory", "GPU", "AI芯片",
                       "华为海思", "中芯国际", "华虹"],
            "新能源": ["新能源", "光伏", "太阳能", "风能", "电池", "锂电",
                       "电动", "EV", "电动车", "氢能", "储能", "逆变器",
                       "宁德时代", "比亚迪", "阳光电源", "隆基绿能"],
            "科技": ["科技", "计算机", "软件", "互联网", "云计算", "大数据",
                     "人工智能", "AI", "机器学习", "深度", "transformer",
                     "SaaS", "云原生", "数字化", "数字"],
            "医药": ["医药", "制药", "生物", "药明康德", "CRO", "CXO",
                     "创新药", "单抗", "疫苗", "医疗器械", "医院",
                     "恒瑞医药", "药明康德", "药石科技"],
            "金融": ["金融", "证券", "银行", "保险", "基金", "券商",
                     "信托", "期货", "资产管理", "金融科技", " fintech",
                     "中信证券", "华泰证券", "东方财富"],
            "消费电子": ["消费电子", "手机", "苹果", "供应链", "电子元件",
                        "面板", "显示", "OLED", "触摸屏", "摄像头",
                         "立讯精密", "歌尔股份", "蓝思科技"],
            "高端制造": ["高端制造", "机器人", "自动化", "工业", "机床",
                        "装备", "智能制造", "工业互联网", "CNC", "伺服"],
            "周期": ["周期", "大宗", "原材料", "矿产", "大宗商品",
                    "铜", "铝", "石油", "煤炭", "钢铁", "化工", "橡胶"],
            "传媒": ["传媒", "影视", "游戏", "广告", "出版", "媒体",
                    "抖音", "快手", "腾讯音乐", "网易游戏", "哔哩哔哩"],
        }
    
    def _load_positive_words(self) -> set:
        """加载正面情感词汇"""
        return {
            "增长", "上涨", "盈利", "超额", "利好", "业绩", "突破",
            "强势", "强劲", "乐观", "看好", "上涨", "上涨", "繁荣",
            "创新", "领先", "第一", "最强", "最佳", "高景气", "爆发",
            "利好", "收益", "分红", "回购", "增持", "买入", "推荐",
            "超预期", "翻倍", "涨停", "放量", "净流入", "增持",
            "政策", "扶持", "补贴", "驱动", "推动", "提振", "促进",
            "机遇", "机会", "潜力", "空间", "广阔", "巨大", "显著",
            "新", "新", "新时代", "新发展", "新模式", "新业态",
            "国产替代", "自主可控", "卡脖子", "安全", "独立",
            "碳中和", "碳达峰", "环保", "绿色", "可持续", "ESG",
            "智能化", "数字化", "转型升级", "改革", "开放",
            "高质量", "高质量发展", "创新驱动", "科技进步",
            "业绩预增", "业绩预告", "年报", "财报", "盈利预告",
        }
    
    def _load_negative_words(self) -> set:
        """加载负面情感词汇"""
        return {
            "下跌", "亏损", "下滑", "下降", "不及预期", "低于",
            "疲软", "弱势", "悲观", "看空", "减仓", "卖出", "减持",
            "警告", "风险", "危机", "暴雷", "退市", "处罚", "监管",
            "利空", "拖累", "承压", "困难", "困境", "挑战", "压力",
            "下调", "降评级", "降目标价", "降增速", "降利润",
            "大幅", "惨重", "巨额", "爆炸性", "灾难性", "悲剧性",
            "取消", "终止", "放弃", "暂停", "延期", "延迟", "延误",
            "竞争", "内卷", "价格战", "同质化", "低毛利", "低质量",
            "债务", "负债", "杠杆", "资金链", "现金流", "破产",
            "诉讼", "纠纷", "质疑", "造假", "财务造假", "欺诈",
            "负面报道", "负面舆情", "丑闻", "曝光", "曝光",
        }
    
    def extract_sentiment(self, text: str) -> float:
        """从文本中提取情感分数，范围[-1, 1]"""
        if not text or len(text.strip()) == 0:
            return 0.0
        
        # 标准化文本：小写化（中文无空格，不能 split()——否则整句成单 token，
        # 词表词永远匹配不上 → 中文情绪恒 0）。改为对词表词做子串匹配。
        text_lower = text.lower()

        # 统计正负词出现次数（子串匹配）
        pos_count = sum(1 for w in self.positive_words if w in text_lower)
        neg_count = sum(1 for w in self.negative_words if w in text_lower)
        
        total = pos_count + neg_count
        if total == 0:
            return 0.0
        
        # 情感得分 = (正 - 负) / (正 + 负)，标准化到[-1, 1]
        score = (pos_count - neg_count) / total
        
        return max(-1.0, min(1.0, score))
    
    def extract_signals(self, news_headline: str, news_content: str, 
                       etf_code: str, sector: str, timestamp: str,
                       source: str) -> List[NewsSignal]:
        """从一篇新闻中提取所有相关ETF信号"""
        combined_text = f"{news_headline} {news_content}"
        
        # 获取该行业的关键词
        keywords = self.sector_keywords.get(sector, [])
        
        # 检查标题和内容中是否包含行业关键词（更精确匹配）
        title_matches = []
        content_matches = []
        
        for kw in keywords:
            if kw.lower() in news_headline.lower():
                title_matches.append(kw)
            if kw.lower() in news_content.lower():
                if kw not in content_matches:
                    content_matches.append(kw)
        
        # 总匹配关键词（去重）
        all_matches = list(set(title_matches + content_matches))
        
        # 计算信号强度 = (匹配关键词数 / 该行业总关键词基数) * 权重调整
        # 标题匹配更重要，给予更高权重
        headline_weight = 0.7
        content_weight = 0.3
        max_keywords = max(len(keywords), 1)
        
        signal_strength = (len(title_matches) * headline_weight + len(content_matches) * content_weight) / max_keywords
        signal_strength = max(0.0, min(1.0, signal_strength))  # 标准化到[0,1]
        
        # 提取整体情感
        sentiment = self.extract_sentiment(combined_text)
        
        # 创建信号对象（仅当有实际关键词匹配或信号强度足够时才产生信号）
        if len(all_matches) > 0 or signal_strength > 0.1:
            signal = NewsSignal(
                etf_code=etf_code,
                sector=sector,
                sentiment_score=sentiment,
                signal_strength=signal_strength,
                keyword_matches=all_matches[:5],  # 最多记录前5个匹配关键词
                timestamp=timestamp,
                source=source,
                headline=news_headline[:100] + "..." if len(news_headline) > 100 else news_headline,
            )
            return [signal]
        
        return []  # 如果没有足够的信号，返回空列表
    
    def process_batch(self, news_items: List[Dict]) -> List[NewsSignal]:
        """批量处理新闻项并返回所有信号"""
        all_signals = []
        for item in news_items:
            try:
                signals = self.extract_signals(
                    headline=item.get("headline", ""),
                    content=item.get("content", ""),
                    etf_code=item.get("etf_code", ""),
                    sector=item.get("sector", ""),
                    timestamp=item.get("timestamp", ""),
                    source=item.get("source", "")
                )
                all_signals.extend(signals)
            except Exception as e:
                logger.error(f"Failed to process news item: {e}")
                continue
        return all_signals


# 全局实例（供pipeline导入使用）
_extractor = None


def get_extractor() -> NewsSignalExtractor:
    """获取或创建全局提取器实例（单例模式）"""
    global _extractor
    if _extractor is None:
        _extractor = NewsSignalExtractor()
    return _extractor


def process_news_item(headline: str, content: str, etf_code: str, sector: str, 
                      timestamp: str = "", source: str = "unknown") -> List[NewsSignal]:
    """便捷函数：处理单条新闻并返回信号列表"""
    extractor = get_extractor()
    return extractor.extract_signals(headline, content, etf_code, sector, timestamp, source)
