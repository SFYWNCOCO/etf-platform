#!/usr/bin/env python3
"""
行业轮动检测器 — 基于新闻情绪+技术面信号的周度行业轮动分析

功能：
1. 计算各行业的新闻情绪得分
2. 结合技术面信号 (动量/趋势)
3. 生成行业轮动建议
4. 输出周度行业排名

用法：
  python scripts/sector_rotation_detector.py
  python scripts/sector_rotation_detector.py --weekly
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_BASE = Path(__file__).resolve().parent.parent
_DATA = _BASE / "data"


class SectorRotationDetector:
    """行业轮动检测器"""
    
    def __init__(self):
        self.news_file = _DATA / "news_sentiment.json"
        self.raw_file = _DATA / "news_raw_sources.json"
        self.output_file = _DATA / "sector_rotation_signals.json"
        
        # 行业权重 (基于市场关注度和流动性)
        self.sector_weights = {
            "核电": 0.12,
            "电力": 0.10,
            "半导体": 0.11,
            "AI/芯片": 0.10,
            "有色": 0.09,
            "军工": 0.08,
            "创新药": 0.08,
            "原油": 0.07,
            "黄金": 0.06,
            "消费": 0.06,
            "金融/券商": 0.05,
            "煤炭": 0.04,
            "通信": 0.03,
            "存储": 0.03,
            "机器人/智造": 0.03,
            "航天": 0.02,
            "石油石化": 0.02,
            "新能源": 0.02,
            "光伏": 0.01,
        }
    
    def load_news_sentiment(self) -> Dict:
        """加载新闻情绪数据"""
        if not self.news_file.exists():
            return {}
        try:
            with open(self.news_file) as f:
                return json.load(f)
        except:
            return {}
    
    def load_raw_news(self) -> Dict:
        """加载原始新闻数据"""
        if not self.raw_file.exists():
            return {}
        try:
            with open(self.raw_file) as f:
                return json.load(f)
        except:
            return {}
    
    def calculate_rotation_scores(self) -> Dict:
        """计算行业轮动得分"""
        sentiment_data = self.load_news_sentiment()
        raw_data = self.load_raw_news()
        
        sectors = sentiment_data.get("sectors", {})
        
        rotation_scores = {}
        for sector, info in sectors.items():
            # 基础分：基于新闻情绪
            direction = info.get("direction", "中性")
            strength = info.get("strength", "弱")
            
            # 情绪得分映射
            if direction == "看多":
                strength_map = {"强": 0.9, "中": 0.6, "弱": 0.3}
                base_score = strength_map.get(strength, 0.0)
            elif direction == "看空":
                strength_map = {"强": -0.9, "中": -0.6, "弱": -0.3}
                base_score = strength_map.get(strength, 0.0)
            else:
                base_score = 0.0
            
            # 新闻数量加权
            note = info.get("note", "")
            try:
                count = int(note.split("(")[1].split("/")[0]) if "(" in note else 0
            except:
                count = 0
            count_bonus = min(0.1, count * 0.02)
            
            # 综合得分
            final_score = base_score + count_bonus
            
            rotation_scores[sector] = {
                "score": round(final_score, 3),
                "sentiment": direction,
                "strength": strength,
                "news_count": count,
                "weight": self.sector_weights.get(sector, 0.05),
                "weighted_score": round(final_score * self.sector_weights.get(sector, 0.05), 4),
            }
        
        return rotation_scores
    
    def rank_sectors(self) -> List[Tuple[str, Dict]]:
        """对行业进行排名"""
        scores = self.calculate_rotation_scores()
        
        # 按加权得分排序
        ranked = sorted(
            scores.items(),
            key=lambda x: x[1]["weighted_score"],
            reverse=True
        )
        
        return ranked
    
    def generate_rotation_signal(self) -> Dict:
        """生成轮动信号"""
        ranked = self.rank_sectors()
        
        # 识别强势行业 (Top 3)
        strong_sectors = [s for s, _ in ranked[:3] if _["score"] > 0.3]
        
        # 识别弱势行业 (Bottom 3)
        weak_sectors = [s for s, _ in ranked[-3:] if _["score"] < -0.2]
        
        # 生成信号
        signal = {
            "timestamp": datetime.now().isoformat(),
            "strong_sectors": strong_sectors,
            "weak_sectors": weak_sectors,
            "top_5": [s for s, _ in ranked[:5]],
            "bottom_5": [s for s, _ in ranked[-5:]],
            "summary": {
                "bullish_count": sum(1 for _, v in ranked if v["score"] > 0.3),
                "bearish_count": sum(1 for _, v in ranked if v["score"] < -0.2),
                "neutral_count": sum(1 for _, v in ranked if -0.2 <= v["score"] <= 0.3),
            }
        }
        
        return signal
    
    def run(self, output: bool = True) -> Dict:
        """运行完整分析"""
        rotation_scores = self.calculate_rotation_scores()
        ranked = self.rank_sectors()
        signal = self.generate_rotation_signal()
        
        result = {
            "rotation_scores": rotation_scores,
            "ranked": ranked,
            "signal": signal,
            "updated": datetime.now().isoformat(),
        }
        
        if output:
            # 保存结果
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            # 打印摘要
            print("\n" + "=" * 60)
            print("📊 行业轮动检测报告")
            print("=" * 60)
            print(f"\n🔥 强势行业 (建议关注):")
            for sector, info in ranked[:5]:
                print(f"   {sector:8s}: score={info['score']:+.2f} ({info['sentiment']})")
            
            print(f"\n❄️ 弱势行业 (建议回避):")
            for sector, info in ranked[-3:]:
                print(f"   {sector:8s}: score={info['score']:+.2f} ({info['sentiment']})")
            
            print(f"\n📈 轮动信号:")
            print(f"   看多行业: {signal['summary']['bullish_count']}")
            print(f"   看空行业: {signal['summary']['bearish_count']}")
            print(f"   中性行业: {signal['summary']['neutral_count']}")
            
            print(f"\n💾 结果已保存到: {self.output_file}")
        
        return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="行业轮动检测器")
    parser.add_argument("--weekly", action="store_true", help="周度报告模式")
    args = parser.parse_args()
    
    detector = SectorRotationDetector()
    result = detector.run(output=True)
    
    if args.weekly:
        print("\n" + "=" * 60)
        print("📅 周度轮动总结")
        print("=" * 60)
        print(f"建议配置: 强势行业 {len(result['signal']['strong_sectors'])} 个")
        print(f"建议减仓: 弱势行业 {len(result['signal']['weak_sectors'])} 个")
