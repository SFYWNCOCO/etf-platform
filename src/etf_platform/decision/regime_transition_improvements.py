# -*- coding: utf-8 -*-
"""Regime Transition 回测验证框架 — 改进方案2

解决的核心问题：
1. 转换概率未校准 — softmax-like归一化无历史验证
2. 指标预测力未知 — 4个先行指标中哪些真正有预测力？
3. 权重无实证支撑 — 只有fearful regime有数据，其他是主观先验
4. 没有Brier score / log loss评估

设计原则：
- 每轮预测记录→10日后验证→累积性能矩阵
- 自动计算每个指标的预测力（与regime转换的相关性）
- 支持滚动窗口权重更新
"""
import json
import logging
import math
import statistics
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform/
DATA_DIR = BASE / "data" / "live_cache"
TRANSITION_LOG = DATA_DIR / "transition_predictions.jsonl"
TRANSITION_VERIFY = DATA_DIR / "transition_verifications.jsonl"


# ── 数据结构 ──────────────────────────────────────────────────────────

@dataclass(slots=True)
class TransitionRecord:
    """一次预测记录的完整快照。"""
    date: str
    timestamp: str
    current_regime: str
    qvix_50: float
    qvix_500: float

    # 预测概率
    prob_stay: float
    prob_improve: float
    prob_worsen: float

    # 原始指标
    breadth_pct: float
    vol_trend: float
    volume_signal: float
    momentum_signal: float

    # 预测置信度
    confidence: str

    # 前瞻权重
    blended_weights: dict = field(default_factory=dict)


@dataclass(slots=True)
class VerificationRecord:
    """一次预测的验证结果。"""
    prediction_date: str
    verification_date: str
    current_regime: str
    actual_regime_after: str  # 10日后的实际regime

    # 预测是否正确
    predicted_direction: str  # "stay", "improve", "worsen"
    actual_direction: str     # "stay", "improve", "worsen"
    correct: bool

    # 概率校准
    predicted_prob: float     # 预测的对应方向概率
    brier_score: float        # Brier score for this prediction
    log_loss: float           # Log loss for this prediction

    # 各指标与实际方向的关系
    breadth_at_pred: float
    vol_trend_at_pred: float
    volume_at_pred: float
    momentum_at_pred: float
    breadth_at_verify: float
    vol_trend_at_verify: float
    volume_at_verify: float
    momentum_at_verify: float


# ── 工具函数 ──────────────────────────────────────────────────────────

REGIME_ORDER = ["complacent", "normal", "cautious", "fearful"]
REGIME_SCORE = {"complacent": 0, "normal": 1, "cautious": 2, "fearful": 3}


def regime_to_score(regime: str) -> int:
    return REGIME_SCORE.get(regime, 1)


def direction_from_regimes(from_r: str, to_r: str) -> str:
    """从两个regime判断方向。"""
    fs = regime_to_score(from_r)
    ts = regime_to_score(to_r)
    if ts == fs:
        return "stay"
    elif ts < fs:
        return "improve"
    else:
        return "worsen"


def compute_brier_score(predicted_prob: float, actual_outcome: int) -> float:
    """计算单个预测的Brier score。

    Args:
        predicted_prob: 预测的概率 [0, 1]
        actual_outcome: 实际结果 (0或1)
    """
    return (predicted_prob - actual_outcome) ** 2


def compute_log_loss(predicted_prob: float, actual_outcome: int) -> float:
    """计算单个预测的对数损失。"""
    p = max(min(predicted_prob, 1 - 1e-10), 1e-10)
    return -(actual_outcome * math.log(p) + (1 - actual_outcome) * math.log(1 - p))


# ── 回测引擎 ──────────────────────────────────────────────────────────

class TransitionBacktester:
    """状态转换预测的回测验证引擎。

    工作流程：
    1. 从 TRANSITION_LOG 读取历史预测
    2. 对于每条预测，查找10天后的实际QVIX regime
    3. 计算预测准确率、Brier score、log loss
    4. 分析每个指标的预测力（与方向变化的相关性）
    5. 输出性能报告
    """

    def __init__(self):
        self.predictions: list[TransitionRecord] = []
        self.verifications: list[VerificationRecord] = []

    def load_predictions(self, log_path: Optional[Path] = None) -> int:
        """从JSONL文件加载历史预测。"""
        path = log_path or TRANSITION_LOG
        if not path.exists():
            logger.warning("No prediction log found at %s", path)
            return 0

        count = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    rec = TransitionRecord(**d)
                    self.predictions.append(rec)
                    count += 1
                except (TypeError, KeyError, json.JSONDecodeError) as e:
                    logger.debug("Skipping invalid prediction record: %s", e)
        return count

    def _get_actual_regime_after_days(self, base_date: str, days_ahead: int = 10) -> Optional[str]:
        """获取base_date之后days_ahead天的实际QVIX regime。

        简化实现：从kline数据计算已实现波动率作为代理。
        完整版需要从历史QVIX数据获取。
        """
        try:
            from etf_platform.data.kline import get_trend

            # 用10日后的价格变化作为regime proxy
            # 这是一个近似 — 理想情况应该有历史QVIX时间序列
            trend = get_trend("510050")  # 上证50ETF
            if trend and trend.change_10d is not None:
                # 用10日收益率映射到regime
                # 简化规则：收益率 > 2% → complacent, > 0% → normal, < -2% → cautious, < -5% → fearful
                ret = trend.change_10d
                if ret > 2:
                    return "complacent"
                elif ret > 0:
                    return "normal"
                elif ret > -2:
                    return "cautious"
                else:
                    return "fearful"
        except Exception as e:
            logger.debug("Failed to get actual regime: %s", e)
        return None

    def verify_prediction(self, pred: TransitionRecord, days_ahead: int = 10) -> Optional[VerificationRecord]:
        """验证单条预测。"""
        actual_regime = self._get_actual_regime_after_days(pred.date, days_ahead)
        if actual_regime is None:
            return None

        # 判断实际方向
        actual_dir = direction_from_regimes(pred.current_regime, actual_regime)

        # 判断预测方向（取概率最高的方向）
        probs = {
            "stay": pred.prob_stay,
            "improve": pred.prob_improve,
            "worsen": pred.prob_worsen,
        }
        predicted_dir = max(probs, key=probs.get)

        # 是否正确
        correct = predicted_dir == actual_dir

        # Brier score: one-hot encoding of actual direction
        actual_onehot = {"stay": 1.0, "improve": 0.0, "worsen": 0.0}
        actual_onehot[actual_dir] = 1.0
        predicted_prob_for_actual = probs[actual_dir]
        brier = compute_brier_score(predicted_prob_for_actual, actual_onehot[actual_dir])

        # Log loss
        logloss = compute_log_loss(predicted_prob_for_actual, actual_onehot[actual_dir])

        verification = VerificationRecord(
            prediction_date=pred.date,
            verification_date=date.today().isoformat(),
            current_regime=pred.current_regime,
            actual_regime_after=actual_regime,
            predicted_direction=predicted_dir,
            actual_direction=actual_dir,
            correct=correct,
            predicted_prob=round(predicted_prob_for_actual, 3),
            brier_score=round(brier, 4),
            log_loss=round(logloss, 4),
            breadth_at_pred=pred.breadth_pct,
            vol_trend_at_pred=pred.vol_trend,
            volume_at_pred=pred.volume_signal,
            momentum_at_pred=pred.momentum_signal,
            breadth_at_verify=0.0,  # placeholder
            vol_trend_at_verify=0.0,
            volume_at_verify=0.0,
            momentum_at_verify=0.0,
        )

        self.verifications.append(verification)
        return verification

    def run_full_backtest(self, days_ahead: int = 10) -> dict:
        """运行完整的回测分析。"""
        if not self.predictions:
            return {"error": "No predictions loaded"}

        print(f"\n{'=' * 60}")
        print(f"🔮 状态转换预测回测 — {len(self.predictions)} 条记录")
        print(f"{'=' * 60}")

        verified = []
        for pred in self.predictions:
            v = self.verify_prediction(pred, days_ahead)
            if v:
                verified.append(v)

        if not verified:
            return {"error": "No verifications completed"}

        # ── 整体统计 ────────────────────────────────────────────────
        total = len(verified)
        correct_count = sum(1 for v in verified if v.correct)
        accuracy = correct_count / total

        avg_brier = statistics.mean([v.brier_score for v in verified])
        avg_logloss = statistics.mean([v.log_loss for v in verified])

        # 随机基线：猜stay（假设regime有惯性）
        stay_rate = sum(1 for v in verified if v.actual_direction == "stay") / total
        random_baseline = max(stay_rate, 1/3)  # 三选一

        print(f"\n  总预测数: {total}")
        print(f"  正确数:   {correct_count}/{total}")
        print(f"  准确率:   {accuracy:.1%}")
        print(f"  随机基线: {random_baseline:.1%} (猜{max('stay', 'improve' if stay_rate < 0.33 else 'worsen')})")
        print(f"  超额收益:  {'+' if accuracy > random_baseline else ''}{accuracy - random_baseline:.1%}")
        print(f"\n  平均Brier Score: {avg_brier:.4f} (越低越好, 随机基线≈0.22)")
        print(f"  平均Log Loss:    {avg_logloss:.4f} (越低越好, 随机基线≈1.10)")

        # ── 按regime分解 ────────────────────────────────────────────
        print("\n  ── 按当前regime分解 ──")
        regime_stats: dict[str, dict] = {}
        for v in verified:
            reg = v.current_regime
            if reg not in regime_stats:
                regime_stats[reg] = {"total": 0, "correct": 0, "briers": [], "loglosses": []}
            regime_stats[reg]["total"] += 1
            if v.correct:
                regime_stats[reg]["correct"] += 1
            regime_stats[reg]["briers"].append(v.brier_score)
            regime_stats[reg]["loglosses"].append(v.logloss)

        for reg, stats in sorted(regime_stats.items()):
            n = stats["total"]
            acc = stats["correct"] / n if n > 0 else 0
            avg_b = statistics.mean(stats["briers"]) if stats["briers"] else 0
            print(f"    {reg:12s}: n={n:3d}, 准确率={acc:.1%}, avg_Brier={avg_b:.4f}")

        # ── 指标预测力分析 ──────────────────────────────────────────
        print("\n  ── 指标预测力分析 ──")
        metric_names = ["breadth", "vol_trend", "volume", "momentum"]
        metric_keys = [
            ("breadth_at_pred", "breadth_at_verify"),
            ("vol_trend_at_pred", "vol_trend_at_verify"),
            ("volume_at_pred", "volume_at_verify"),
            ("momentum_at_pred", "momentum_at_verify"),
        ]

        for name, (pred_key, verify_key) in zip(metric_names, metric_keys):
            preds_vals = [getattr(v, pred_key) for v in verified]
            # 计算该指标值与方向正确性的相关性
            # 简化：分组比较
            high_vals = [v for v in verified if getattr(v, pred_key) > 0]
            low_vals = [v for v in verified if getattr(v, pred_key) <= 0]

            high_acc = sum(1 for v in high_vals if v.correct) / len(high_vals) if high_vals else 0
            low_acc = sum(1 for v in low_vals if v.correct) / len(low_vals) if low_vals else 0

            print(f"    {name:12s}: high_group_acc={high_acc:.1%} (n={len(high_vals)}), "
                  f"low_group_acc={low_acc:.1%} (n={len(low_vals)})")

        # ── 保存验证结果 ────────────────────────────────────────────
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(TRANSITION_VERIFY, "a", encoding="utf-8") as f:
                for v in verified[-10:]:  # 只追加最近10条避免文件过大
                    f.write(json.dumps(asdict(v), ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("Failed to save verification records: %s", e)

        return {
            "total": total,
            "correct": correct_count,
            "accuracy": round(accuracy, 4),
            "random_baseline": round(random_baseline, 4),
            "outperformance": round(accuracy - random_baseline, 4),
            "avg_brier": round(avg_brier, 4),
            "avg_logloss": round(avg_logloss, 4),
            "by_regime": {
                k: {
                    "total": v["total"],
                    "correct": v["correct"],
                    "accuracy": round(v["correct"] / v["total"], 4) if v["total"] > 0 else 0,
                    "avg_brier": round(statistics.mean(v["briers"]), 4) if v["briers"] else 0,
                }
                for k, v in regime_stats.items()
            },
            "verified_count": len(verified),
        }

    def save_verification(self, verification: VerificationRecord, log_path: Optional[Path] = None) -> None:
        """保存单条验证记录到JSONL。"""
        path = log_path or TRANSITION_VERIFY
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(verification), ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("Failed to save verification: %s", e)


# ── 集成：增强版 predict_transition ──────────────────────────────────

def predict_transition_with_logging(
    current_regime: Optional[str] = None,
    log_prediction: bool = True,
) -> dict:
    """增强版状态转换预测 — 自动记录预测供后续验证。

    调用原 regime_transition.py 的 predict_transition，但额外：
    1. 记录预测到 JSONL
    2. 返回结构化结果
    """
    try:
        from etf_platform.decision.regime_transition import predict_transition as orig_predict

        pred = orig_predict(current_regime)

        result = {
            "current_regime": pred.current_regime,
            "prob_stay": pred.prob_stay,
            "prob_improve": pred.prob_improve,
            "prob_worsen": pred.prob_worsen,
            "breadth_pct": pred.breadth_pct,
            "vol_trend": pred.vol_trend,
            "volume_signal": pred.volume_signal,
            "momentum_signal": pred.momentum_signal,
            "confidence": pred.confidence,
            "blended_weights": pred.blended_weights,
            "timestamp": datetime.now().isoformat(),
        }

        if log_prediction:
            record = TransitionRecord(
                date=date.today().isoformat(),
                timestamp=result["timestamp"],
                current_regime=pred.current_regime,
                qvix_50=20.0,  # placeholder — should come from get_regime
                qvix_500=22.0,
                prob_stay=pred.prob_stay,
                prob_improve=pred.prob_improve,
                prob_worsen=pred.prob_worsen,
                breadth_pct=pred.breadth_pct,
                vol_trend=pred.vol_trend,
                volume_signal=pred.volume_signal,
                momentum_signal=pred.momentum_signal,
                confidence=pred.confidence,
                blended_weights=pred.blended_weights,
            )
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                with open(TRANSITION_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
            except OSError as e:
                logger.warning("Failed to log prediction: %s", e)

        return result

    except Exception as e:
        logger.error("predict_transition_with_logging failed: %s", e)
        return {"error": str(e)}


if __name__ == "__main__":
    bt = TransitionBacktester()

    # 加载历史预测
    n = bt.load_predictions()
    print(f"加载了 {n} 条历史预测")

    # 运行回测
    if n > 0:
        results = bt.run_full_backtest()
        print(f"\n回测完成: {results}")
    else:
        print("\n无历史预测数据，运行一次新预测...")
        result = predict_transition_with_logging(log_prediction=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
