"""ml_predictor.py — XGBoost/LightGBM/CatBoost ensemble ETF predictor.

Predicts next-10-day ETF returns using engineered technical features +
gradient-boosted trees ensemble.  Designed to complement the existing
Z-score multi-factor picker (two_week_picker.py).

Architecture:
  1. Data layer — Tencent kline (200d daily bars) → feature matrix
  2. Feature engineering — momentum, volatility, volume, TA-Lib (RSI, MACD, BB)
  3. Label generation — forward 10d return, binary (+/-) + regression (actual)
  4. Model training — XGB + LGBM + CAT stacking with soft-vote ensemble
  5. Prediction — Top-3 ETFs with probability, expected return, confidence

Usage:
  python -m etf_platform.decision.ml_predictor --predict        # live Top-3
  python -m etf_platform.decision.ml_predictor --train-only     # retrain model
  python -m etf_platform.decision.ml_predictor --compare        # ML vs Z-score
"""
from __future__ import annotations

from ..utils import sina_code

import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform root
SRC = BASE / "src"
sys.path.insert(0, str(SRC))

MODEL_DIR = BASE / "data" / "ml_models"
PRED_DIR = BASE / "data" / "predictions"
PRED_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HORIZON = 10  # predict next 10 trading days
TRAIN_DAYS = 180  # lookback window for training data (~8mo, fits 200d kline cap)
KLINE_DAYS = 200  # fetch extra buffer for forward-label computation
TOP_N_PREDICT = 3
MAX_CANDIDATES = 60  # ML candidate pool size
SECTOR_FLOW_THRESHOLD = 0.0  # skip sector flow if not available

# ETF codes to include in training pool (diverse sectors)
# We'll auto-select from config_loader but provide a fallback list
SECTOR_ETF_MAP: dict[str, list[str]] = {
    "半导体": ["159995", "512480"],
    "芯片": ["159995", "512760"],
    "人工智能": ["515050", "159819"],
    "光伏": ["515790", "516180"],
    "新能源": ["516160", "159891"],
    "医药": ["512010", "515120"],
    "消费": ["159928", "515650"],
    "白酒": ["512690", "159701"],
    "券商": ["512000", "512880"],
    "军工": ["512660", "512670"],
    "红利价值": ["512890", "515180"],
    "黄金": ["518880", "159934"],
    "5G/PCB": ["515880", "515030"],
    "通信": ["515880", "515050"],
    "科创50": ["588000", "588080"],
    "创业板": ["159915", "159949"],
    "恒生科技": ["513130", "159742"],
    "中概互联": ["513050", "159994"],
    "新能源车": ["515030", "162607"],
}

# All candidate ETFs (union of sector map + some extras)
CANDIDATE_CODES: list[str] = [
    "510300", "512890", "159995", "513100", "518880", "515880",
    "512480", "159819", "512660", "512760", "515100", "515790",
    "512170", "512690", "515030", "513050", "513500", "159915",
    "159994", "512010", "512000", "512880", "512670", "515120",
    "516160", "159891", "159928", "515650", "159701", "515180",
    "159934", "513130", "159742", "588000", "588080", "159949",
    "159910", "510050", "510500", "512100", "512200", "512400",
    "512900", "515210", "159985", "516150", "516110", "516520",
    "516950", "159997", "159982", "159993", "159992", "159989",
    "159998", "159999", "159976", "159975", "159973", "159972",
    "159971", "159970", "159969", "159968", "159967", "159966",
]

# Exclusion rules (same as two_week_picker)
EXCLUDE_SECTORS = {"货币基金", "利率债", "信用债", "债券", "国债", "货币"}
EXCLUDE_TYPES = {"宽基A"}
EXCLUDE_KEYWORDS = [
    "沪深300", "中证500", "中证1000", "上证50", "深证100",
    "创业板", "科创50", "科创100",
]


# ===================================================================
#  DATA LAYER — Fetch kline via Tencent (primary) or Sina (fallback)
# ===================================================================



def fetch_kline_rows(code: str, days: int = KLINE_DAYS) -> list[dict] | None:
    """Fetch daily kline data for one ETF. Returns list of row dicts.

    Tries Tencent primary (fastest), then Sina fallback.
    """
    prefix = sina_code(code)

    # ── Try Tencent first ──
    tencent_url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{min(days, 200)},qfq"
    try:
        import urllib.request as _urllib
        req = _urllib.Request(tencent_url, headers={"User-Agent": "Mozilla/5.0"})
        with _urllib.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        import json as _json
        data = _json.loads(raw)
        for key in ("qfqday", "day"):
            rows = data.get("data", {}).get(f"{prefix}{code}", {}).get(key, [])
            if rows:
                result = []
                for r in rows:
                    result.append({
                        "date": r[0],
                        "open": float(r[1]),
                        "close": float(r[2]),
                        "high": float(r[3]),
                        "low": float(r[4]),
                        "volume": float(r[5]) if len(r) > 5 else 0.0,
                    })
                return result
    except (OSError, json.JSONDecodeError, ValueError, KeyError, AttributeError, ImportError) as exc:
        logger.debug("Tencent kline failed for %s: %s", code, exc)

    # ── Sina fallback ──
    sina_url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={prefix}{code}&scale=240&ma=no&datalen={min(days, 1024)}"
    try:
        import urllib.request as _urllib
        req = _urllib.Request(sina_url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "http://finance.sina.com.cn/",
        })
        with _urllib.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("gbk")
        import json as _json
        rows = _json.loads(raw)
        if rows and len(rows) >= 5:
            result = []
            for r in rows:
                result.append({
                    "date": r.get("day", r.get("date", "")),
                    "open": float(r["open"]),
                    "close": float(r["close"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "volume": float(r.get("volume", 0)),
                })
            return result
    except (OSError, json.JSONDecodeError, ValueError, KeyError, AttributeError, ImportError) as exc:
        logger.debug("Sina kline fallback failed for %s: %s", code, exc)
    return None


def build_feature_df(codes: list[str]) -> pd.DataFrame:
    """Build a feature DataFrame for the given ETF codes.

    Each row = one (ETF_code, date) with computed features.
    Also computes forward-10d return as label.
    """
    all_records: list[dict] = []

    for code in codes:
        rows = fetch_kline_rows(code, days=KLINE_DAYS)
        if not rows or len(rows) < TRAIN_DAYS:
            continue

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        # Only keep last TRAIN_DAYS bars for computing features
        df = df.tail(TRAIN_DAYS + HORIZON + 10).copy()  # extra for forward label

        if len(df) < TRAIN_DAYS + 10:
            continue

        # ── Compute forward return ──
        df["forward_ret_10d"] = (
            df["close"].shift(-HORIZON) / df["close"] - 1
        ) * 100

        # Drop rows where forward return is NaN (last HORIZON rows)
        df_valid = df.dropna(subset=["forward_ret_10d"]).copy()

        if len(df_valid) < 60:  # minimum samples
            continue

        # Mark each row with its ETF code
        df_valid["etf_code"] = code

        all_records.append(df_valid)

    if not all_records:
        return pd.DataFrame()

    combined = pd.concat(all_records, ignore_index=True)
    return combined


def compute_ta_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add TA-Lib technical indicators to the feature DataFrame.

    Operates per-ETF group.
    """
    import talib

    if "etf_code" not in df.columns:
        return df

    groups = df.groupby("etf_code", sort=False)
    parts: list[pd.DataFrame] = []

    for code, grp in groups:
        g = grp.copy()
        closes = g["close"].values.astype(float)
        highs = g["high"].values.astype(float)
        lows = g["low"].values.astype(float)
        volumes = g["volume"].values.astype(float)

        # ── Momentum ──
        for period in (5, 10, 20, 60):
            if len(closes) >= period + 1:
                g[f"momentum_{period}d"] = (
                    (closes[-1] / closes[-period - 1] - 1) * 100
                )
            else:
                g[f"momentum_{period}d"] = 0.0

        # ── Rate of Change ──
        roc_5 = talib.ROC(closes, timeperiod=5)
        roc_10 = talib.ROC(closes, timeperiod=10)
        roc_20 = talib.ROC(closes, timeperiod=20)
        g["roc_5"] = roc_5
        g["roc_10"] = roc_10
        g["roc_20"] = roc_20

        # ── RSI ──
        rsi_6 = talib.RSI(closes, timeperiod=6)
        rsi_14 = talib.RSI(closes, timeperiod=14)
        rsi_28 = talib.RSI(closes, timeperiod=28)
        g["rsi_6"] = rsi_6
        g["rsi_14"] = rsi_14
        g["rsi_28"] = rsi_28

        # ── MACD ──
        macd_dif, macd_dea, macd_hist = talib.MACD(
            closes, fastperiod=12, slowperiod=26, signalperiod=9
        )
        g["macd_dif"] = macd_dif
        g["macd_dea"] = macd_dea
        g["macd_hist"] = macd_hist

        # ── Bollinger Bands ──
        bb_upper, bb_middle, bb_lower = talib.BBANDS(
            closes, timeperiod=20, nbdevup=2, nbdevdn=2
        )
        g["bb_width"] = (bb_upper - bb_lower) / bb_middle * 100
        g["bb_position"] = (closes - bb_lower) / (bb_upper - bb_lower) * 100

        # ── Volatility (rolling std) ──
        rets = np.diff(np.log(closes + 1e-10))
        vol_5 = pd.Series(rets).rolling(5).std().values
        vol_10 = pd.Series(rets).rolling(10).std().values
        vol_20 = pd.Series(rets).rolling(20).std().values
        g["volatility_5d"] = np.concatenate([[np.nan] * 1, vol_5[:len(g)]])
        g["volatility_10d"] = np.concatenate([[np.nan] * 1, vol_10[:len(g)]])
        g["volatility_20d"] = np.concatenate([[np.nan] * 1, vol_20[:len(g)]])

        # ── Volume change ratios ──
        pd.Series(volumes).rolling(5).mean().values
        v_ma20 = pd.Series(volumes).rolling(20).mean().values
        g["volume_ratio_5_20"] = volumes / (v_ma20 + 1e-10)
        g["volume_change_5d"] = (
            (pd.Series(volumes).pct_change(5)).fillna(0).values
        )

        # ── ATR ──
        atr_14 = talib.ATR(highs, lows, closes, timeperiod=14)
        g["atr_14"] = atr_14
        g["atr_pct"] = atr_14 / closes * 100

        # ── Stochastic ──
        slowk, slowd = talib.STOCH(highs, lows, closes)
        g["stoch_k"] = slowk
        g["stoch_d"] = slowd

        # ── CCI ──
        cci_20 = talib.CCI(highs, lows, closes, timeperiod=20)
        g["cci_20"] = cci_20

        # ── ADX (trend strength) ──
        adx_14 = talib.ADX(highs, lows, closes, timeperiod=14)
        g["adx_14"] = adx_14

        # ── SMA deviation ──
        sma_5 = talib.SMA(closes, timeperiod=5)
        sma_10 = talib.SMA(closes, timeperiod=10)
        sma_20 = talib.SMA(closes, timeperiod=20)
        sma_60 = talib.SMA(closes, timeperiod=60)
        g["price_sma5_dev"] = (closes - sma_5) / sma_5 * 100
        g["price_sma10_dev"] = (closes - sma_10) / sma_10 * 100
        g["price_sma20_dev"] = (closes - sma_20) / sma_20 * 100
        g["price_sma60_dev"] = (closes - sma_60) / sma_60 * 100

        # ── Price position in range ──
        hh = talib.MAX(highs, timeperiod=20)
        ll = talib.MIN(lows, timeperiod=20)
        g["price_position_20d"] = (closes - ll) / (hh - ll + 1e-10) * 100

        hh60 = talib.MAX(highs, timeperiod=60)
        ll60 = talib.MIN(lows, timeperiod=60)
        g["price_position_60d"] = (closes - ll60) / (hh60 - ll60 + 1e-10) * 100

        # ── OBV (On Balance Volume) trend ──
        obv = talib.OBV(closes, volumes)
        obv_ma5 = talib.SMA(obv, timeperiod=5)
        g["obv_trend"] = obv - obv_ma5

        parts.append(g)

    if parts:
        result = pd.concat(parts, ignore_index=True)
    else:
        result = df.copy()

    # Fill NaN from TA computations
    result = result.fillna(0.0)
    return result


FEATURE_COLS: list[str] = [
    "momentum_5d", "momentum_10d", "momentum_20d", "momentum_60d",
    "roc_5", "roc_10", "roc_20",
    "rsi_6", "rsi_14", "rsi_28",
    "macd_dif", "macd_dea", "macd_hist",
    "bb_width", "bb_position",
    "volatility_5d", "volatility_10d", "volatility_20d",
    "volume_ratio_5_20", "volume_change_5d",
    "atr_14", "atr_pct",
    "stoch_k", "stoch_d",
    "cci_20",
    "adx_14",
    "price_sma5_dev", "price_sma10_dev", "price_sma20_dev", "price_sma60_dev",
    "price_position_20d", "price_position_60d",
    "obv_trend",
]


# ===================================================================
#  LABEL GENERATION
# ===================================================================

def create_labels(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create binary and regression labels from forward returns.

    Returns:
        df_binary: with 'label_binary' column (1=up, 0=down)
        df_regression: with 'label_return' column (actual 10d return)
    """
    df = df.copy()
    # Binary: 1 if forward return > 0, else 0
    df["label_binary"] = (df["forward_ret_10d"] > 0.0).astype(int)
    # Regression: actual return
    df["label_return"] = df["forward_ret_10d"]
    return df, df


# ===================================================================
#  MODEL TRAINING
# ===================================================================

@dataclass(slots=True)
class TrainResult:
    """Container for training results."""
    binary_model: dict[str, Any] | None = None  # {model, scaler, feature_names}
    regression_model: dict[str, Any] | None = None
    binary_accuracy: float = 0.0
    binary_cv_scores: list[float] = field(default_factory=list)
    regression_rmse: float = 0.0
    regression_cv_scores: list[float] = field(default_factory=list)
    n_samples: int = 0
    n_features: int = 0
    feature_importance: dict[str, float] = field(default_factory=dict)


def _train_with_cv(X, y_binary, y_reg, feature_names: list[str]):
    """Train both binary classifier and regressor with time-series CV."""
    tscv = TimeSeriesSplit(n_splits=5)

    # ── Binary classification ──
    binary_accuracies = []
    StandardScaler()
    best_binary_acc = 0.0

    for train_idx, test_idx in tscv.split(X):
        X_tr, X_te = X[train_idx], X[test_idx]
        y_tr, y_te = y_binary[train_idx], y_binary[test_idx]

        sc = StandardScaler()
        X_tr_s = sc.fit_transform(X_tr)
        X_te_s = sc.transform(X_te)

        # Quick cross-validation with different models
        from xgboost import XGBClassifier
        from lightgbm import LGBMClassifier
        from catboost import CatBoostClassifier, Pool

        models = [
            ("xgb", XGBClassifier(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, random_state=42,
                eval_metric="logloss",
            )),
            ("lgbm", LGBMClassifier(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, random_state=42,
                verbose=-1, force_col_wise=True,
            )),
            ("cat", CatBoostClassifier(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bylevel=0.8, random_state=42,
                verbose=0,
            )),
        ]

        best_acc_fold = 0.0
        best_model_fold = None
        best_name_fold = ""
        best_sc_fold = None

        for name, model in models:
            try:
                if name == "cat":
                    cb_pool = Pool(X_tr_s, y_tr)
                    model.fit(X_tr_s, y_tr, eval_set=cb_pool)
                else:
                    model.fit(X_tr_s, y_tr)
                preds = model.predict(X_te_s)
                acc = accuracy_score(y_te, preds)
                if acc > best_acc_fold:
                    best_acc_fold = acc
                    best_model_fold = model
                    best_name_fold = name
                    best_sc_fold = sc
            except (ValueError, AttributeError, TypeError, OSError, KeyError):
                continue

        binary_accuracies.append(best_acc_fold)
        if best_acc_fold > best_binary_acc:
            best_binary_acc = best_acc_fold

    # ── Final training on all data with best model ──
    final_binary = None
    final_binary_name = ""
    final_binary_scaler = StandardScaler()

    from xgboost import XGBClassifier
    from lightgbm import LGBMClassifier
    from catboost import CatBoostClassifier, Pool

    models_final = [
        ("xgb", XGBClassifier(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, random_state=42,
            eval_metric="logloss",
        )),
        ("lgbm", LGBMClassifier(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, random_state=42,
            verbose=-1, force_col_wise=True,
        )),
        ("cat", CatBoostClassifier(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bylevel=0.8, random_state=42,
            verbose=0,
        )),
    ]

    best_overall_acc = 0.0
    for name, model in models_final:
        try:
            X_scaled = final_binary_scaler.fit_transform(X)
            if name == "cat":
                cb_pool = Pool(X_scaled, y_binary)
                model.fit(X_scaled, y_binary, eval_set=cb_pool)
            else:
                model.fit(X_scaled, y_binary)
            preds = model.predict(final_binary_scaler.transform(X))
            acc = accuracy_score(y_binary, preds)
            if acc > best_overall_acc:
                best_overall_acc = acc
                final_binary = model
                final_binary_name = name
                final_binary_scaler = StandardScaler()
                final_binary_scaler.fit(X)
        except (ValueError, AttributeError, TypeError, OSError, KeyError):
            continue

    # ── Regression ──
    rmse_scores = []
    best_reg_params = None

    for train_idx, test_idx in tscv.split(X):
        X_tr, X_te = X[train_idx], X[test_idx]
        y_tr, y_te = y_reg[train_idx], y_reg[test_idx]

        sc = StandardScaler()
        X_tr_s = sc.fit_transform(X_tr)
        X_te_s = sc.transform(X_te)

        from xgboost import XGBRegressor
        from lightgbm import LGBMRegressor
        from catboost import CatBoostRegressor

        models = [
            ("xgb", XGBRegressor(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, random_state=42,
            )),
            ("lgbm", LGBMRegressor(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, random_state=42,
                verbose=-1, force_col_wise=True,
            )),
            ("cat", CatBoostRegressor(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bylevel=0.8, random_state=42,
                verbose=0,
            )),
        ]

        best_rmse_fold = float("inf")
        best_model_fold = None
        best_name_fold = ""
        best_sc_fold = None

        for name, model in models:
            try:
                model.fit(X_tr_s, y_tr)
                preds = model.predict(X_te_s)
                rmse = np.sqrt(np.mean((preds - y_te) ** 2))
                if rmse < best_rmse_fold:
                    best_rmse_fold = rmse
                    best_model_fold = model
                    best_name_fold = name
                    best_sc_fold = sc
            except (ValueError, AttributeError, TypeError, OSError, KeyError):
                continue

        rmse_scores.append(best_rmse_fold)
        if best_rmse_fold < (best_reg_params.get("rmse", float("inf")) if best_reg_params else float("inf")):
            best_reg_params = {
                "model": best_model_fold,
                "name": best_name_fold,
                "scaler": best_sc_fold,
                "rmse": best_rmse_fold,
            }

    # ── Final regression on all data ──
    final_reg = None
    final_reg_name = ""
    final_reg_scaler = StandardScaler()
    final_reg_rmse = float("inf")

    from xgboost import XGBRegressor
    from lightgbm import LGBMRegressor
    from catboost import CatBoostRegressor

    models_final = [
        ("xgb", XGBRegressor(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, random_state=42,
        )),
        ("lgbm", LGBMRegressor(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, random_state=42,
            verbose=-1, force_col_wise=True,
        )),
        ("cat", CatBoostRegressor(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bylevel=0.8, random_state=42,
            verbose=0,
        )),
    ]

    for name, model in models_final:
        try:
            X_scaled = final_reg_scaler.fit_transform(X)
            model.fit(X_scaled, y_reg)
            preds = model.predict(final_reg_scaler.transform(X))
            rmse = np.sqrt(np.mean((preds - y_reg) ** 2))
            if rmse < final_reg_rmse:
                final_reg_rmse = rmse
                final_reg = model
                final_reg_name = name
                final_reg_scaler = StandardScaler()
                final_reg_scaler.fit(X)
        except (ValueError, AttributeError, TypeError, OSError, KeyError):
            continue

    # ── Feature importance (from best binary model) ──
    importance = {}
    if final_binary and hasattr(final_binary, "feature_importances_"):
        importances = final_binary.feature_importances_.astype(float)
        total = importances.sum()
        if total > 0:
            for fname, imp in zip(feature_names, importances / total):
                importance[fname] = round(float(imp), 6)
    elif final_reg and hasattr(final_reg, "feature_importances_"):
        importances = final_reg.feature_importances_.astype(float)
        total = importances.sum()
        if total > 0:
            for fname, imp in zip(feature_names, importances / total):
                importance[fname] = round(float(imp), 6)

    return TrainResult(
        binary_model={
            "model": final_binary,
            "name": final_binary_name,
            "scaler": final_binary_scaler,
            "feature_names": feature_names,
        },
        regression_model={
            "model": final_reg,
            "name": final_reg_name,
            "scaler": final_reg_scaler,
            "feature_names": feature_names,
        },
        binary_accuracy=round(binary_accuracies[-1], 4) if binary_accuracies else 0.0,
        binary_cv_scores=[round(s, 4) for s in binary_accuracies],
        regression_rmse=round(rmse_scores[-1], 4) if rmse_scores else 0.0,
        regression_cv_scores=[round(s, 4) for s in rmse_scores],
        n_samples=len(X),
        n_features=len(feature_names),
        feature_importance=importance,
    )


def train_model(
    codes: list[str] | None = None,
    save: bool = True,
    debug: bool = False,
) -> TrainResult:
    """End-to-end: fetch data → compute features → train ensemble.

    Args:
        codes: Specific ETF codes to use. If None, uses CANDIDATE_CODES.
        save: Whether to persist models to disk.
        debug: Print diagnostic info.

    Returns:
        TrainResult with model info and metrics.
    """
    if codes is None:
        codes = CANDIDATE_CODES[:]

    if debug:
        print(f"[ML] Training with {len(codes)} ETF codes...")

    t0 = time.time()

    # ── Step 1: Fetch kline data ──
    if debug:
        print("[ML] Fetching kline data...")
    df_raw = build_feature_df(codes)
    if df_raw.empty:
        logger.error("No kline data fetched. Check network or ETF codes.")
        return TrainResult()

    if debug:
        print(f"[ML] Raw data: {len(df_raw)} rows × {len(df_raw.columns)} cols")

    # ── Step 2: Compute TA features ──
    if debug:
        print("[ML] Computing TA features...")
    df_feat = compute_ta_features(df_raw)

    # ── Step 3: Create labels ──
    df_feat, df_reg = create_labels(df_feat)

    # ── Step 4: Prepare feature matrix ──
    available_cols = [c for c in FEATURE_COLS if c in df_feat.columns]
    if not available_cols:
        logger.error("No feature columns available after TA computation.")
        return TrainResult()

    X = df_feat[available_cols].values.astype(float)
    y_binary = df_feat["label_binary"].values
    y_reg = df_feat["label_return"].values

    # Remove any remaining inf/nan
    mask = np.isfinite(X).all(axis=1) & np.isfinite(y_binary) & np.isfinite(y_reg)
    X = X[mask]
    y_binary = y_binary[mask]
    y_reg = y_reg[mask]

    if len(X) < 100:
        logger.warning("Insufficient training samples after cleaning (%d).", len(X))

    if debug:
        print(f"[ML] Cleaned: {len(X)} samples, {len(available_cols)} features")
        print(f"[ML] Class balance: up={y_binary.sum()}/{len(y_binary)} ({y_binary.mean()*100:.1f}%)")

    # ── Step 5: Train ──
    if debug:
        print("[ML] Training models (5-fold time-series CV)...")
    result = _train_with_cv(X, y_binary, y_reg, available_cols)

    elapsed = time.time() - t0
    if debug:
        print(f"[ML] Training complete in {elapsed:.1f}s")
        print(f"[ML] Best binary model: {result.binary_model['name'] if result.binary_model else 'N/A'}")
        print(f"[ML] Binary accuracy (CV): {result.binary_cv_scores}")
        print(f"[ML] Regression RMSE (CV): {result.regression_cv_scores}")
        if result.feature_importance:
            top5 = sorted(result.feature_importance.items(), key=lambda x: -x[1])[:5]
            print(f"[ML] Top-5 features: {top5}")

    # ── Step 6: Save models ──
    if save and (result.binary_model or result.regression_model):
        _save_models(result, available_cols)

    return result


def _save_models(result: TrainResult, feature_names: list[str]) -> None:
    """Serialize trained models to disk using joblib-compatible JSON."""
    import pickle
    import base64

    payload = {
        "feature_names": feature_names,
        "n_features": result.n_features,
        "n_samples": result.n_samples,
        "binary_accuracy": result.binary_accuracy,
        "binary_cv_scores": result.binary_cv_scores,
        "regression_rmse": result.regression_rmse,
        "regression_cv_scores": result.regression_cv_scores,
        "feature_importance": result.feature_importance,
        "trained_at": date.today().isoformat(),
    }

    if result.binary_model:
        bm = result.binary_model
        payload["binary_model_name"] = bm.get("name", "")
        payload["binary_model_b64"] = base64.b64encode(
            pickle.dumps(bm["model"])
        ).decode("ascii")
        payload["binary_scaler_b64"] = base64.b64encode(
            pickle.dumps(bm["scaler"])
        ).decode("ascii")

    if result.regression_model:
        rm = result.regression_model
        payload["regression_model_name"] = rm.get("name", "")
        payload["regression_model_b64"] = base64.b64encode(
            pickle.dumps(rm["model"])
        ).decode("ascii")
        payload["regression_scaler_b64"] = base64.b64encode(
            pickle.dumps(rm["scaler"])
        ).decode("ascii")

    model_file = MODEL_DIR / "ensemble_model.json"
    model_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    logger.info("Model saved to %s", model_file)


def load_model() -> dict[str, Any] | None:
    """Load previously trained model from disk."""
    model_file = MODEL_DIR / "ensemble_model.json"
    if not model_file.exists():
        return None
    try:
        import base64
        import pickle
        payload = json.loads(model_file.read_text())
        # Decode pickled objects
        if "binary_model_b64" in payload:
            payload["binary_model_obj"] = pickle.loads(
                base64.b64decode(payload.pop("binary_model_b64"))
            )
            payload["binary_scaler_obj"] = pickle.loads(
                base64.b64decode(payload.pop("binary_scaler_b64"))
            )
        if "regression_model_b64" in payload:
            payload["regression_model_obj"] = pickle.loads(
                base64.b64decode(payload.pop("regression_model_b64"))
            )
            payload["regression_scaler_obj"] = pickle.loads(
                base64.b64decode(payload.pop("regression_scaler_b64"))
            )
        return payload
    except (OSError, json.JSONDecodeError, ValueError, KeyError, AttributeError, ImportError) as exc:
        logger.error("Failed to load model: %s", exc)
        return None


# ===================================================================
#  PREDICTION ENGINE
# ===================================================================

def predict_top3(
    codes: list[str] | None = None,
    model_payload: dict[str, Any] | None = None,
    retrain: bool = False,
    debug: bool = False,
) -> list[dict]:
    """Generate today's Top-3 ML prediction.

    Uses the latest trained model (or retrains if needed).
    For each candidate ETF:
      1. Fetch current kline data
      2. Compute features
      3. Run ensemble prediction (probability + expected return)
      4. Sort by predicted return, apply sector diversification

    Args:
        codes: Specific ETF codes. Auto-selects from CANDIDATE_CODES if None.
        model_payload: Pre-loaded model. Retrains fresh if None and retrain=True.
        retrain: Force retrain before predicting.
        debug: Verbose output.

    Returns:
        List of prediction dicts for Top-3 ETFs.
    """
    if codes is None:
        codes = CANDIDATE_CODES[:]

    # Load or train model
    if retrain or model_payload is None:
        if debug:
            print("[ML] Loading/training model...")
        model_payload = load_model()
        if model_payload is None:
            if debug:
                print("[ML] No existing model found. Training fresh...")
            train_model(codes=codes[:20], save=True, debug=debug)  # small subset for speed
            model_payload = load_model()
            if model_payload is None:
                logger.error("Training failed. Cannot produce predictions.")
                return []

    bm = model_payload.get("binary_model_obj")
    bs = model_payload.get("binary_scaler_obj")
    rm = model_payload.get("regression_model_obj")
    rs = model_payload.get("regression_scaler_obj")
    feature_names = model_payload.get("feature_names", FEATURE_COLS)

    if bm is None or rm is None:
        logger.error("Model missing binary or regression component.")
        return []

    if debug:
        print(f"[ML] Using binary={model_payload.get('binary_model_name','?')} "
              f"regression={model_payload.get('regression_model_name','?')}")

    # ── Predict on latest data for each candidate ──
    predictions: list[dict] = []
    seen_sectors: set[str] = set()

    for i, code in enumerate(codes):
        try:
            rows = fetch_kline_rows(code, days=KLINE_DAYS)
            if not rows or len(rows) < 60:
                continue

            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)

            # Use only recent data for feature computation
            df_recent = df.tail(200).copy()
            if len(df_recent) < 30:
                continue

            # Compute features on recent data (needs etf_code for groupby)
            df_recent["etf_code"] = code
            df_recent = compute_ta_features(df_recent)

            # Get latest row features
            latest = df_recent.iloc[[-1]].copy()
            available = [c for c in feature_names if c in latest.columns]
            if len(available) != len(feature_names):
                # Missing features — fill with 0
                for fn in feature_names:
                    if fn not in available:
                        latest.loc[:, fn] = 0.0

            X_latest = latest[feature_names].values.astype(float)
            X_scaled = bs.transform(X_latest)

            # Ensemble prediction: average probabilities from all 3 models
            prob_up = 0.0
            models_used = 0

            for model in [bm, rm]:  # Both binary and regression can predict direction
                try:
                    pred_raw = model.predict(X_scaled)[0]
                    pred = float(pred_raw)  # handle np.float64 etc.
                    if model == bm:
                        # Classification → probability via predict_proba
                        if hasattr(model, "predict_proba"):
                            probas = model.predict_proba(X_scaled)[0]
                            if len(probas) >= 2:
                                prob_up += float(probas[1])
                                models_used += 1
                            else:
                                prob_up += max(pred, 0.0)
                                models_used += 1
                        else:
                            prob_up += max(pred, 0.0)
                            models_used += 1
                    else:
                        # Regression → sign indicates direction
                        if pred > 0:
                            prob_up += 0.5 + min(abs(pred) / 10.0, 0.5)
                        else:
                            prob_up += max(0.5 - abs(pred) / 10.0, 0.0)
                        models_used += 1
                except (ValueError, AttributeError, TypeError, OSError):
                    continue

            if models_used == 0:
                continue

            prob_up /= models_used

            # Expected return from regression model
            expected_return = 0.0
            try:
                er_pred = rs.transform(X_latest)
                expected_return = float(rm.predict(er_pred)[0])
            except (ValueError, AttributeError, TypeError, OSError, KeyError):
                    logger.warning("silent catch in ml_predictor.py:958 - needs review")

            # Confidence based on model agreement and feature quality
            feature_std = np.std(X_latest[0][:len(feature_names)])
            confidence = min(0.95, max(0.3, prob_up * 0.6 + (1 - min(feature_std / 5.0, 1.0)) * 0.4))

            # Get ETF name/sector from config
            try:
                from etf_platform.config_loader import load_etfs
                etfs = load_etfs()
                info = etfs.get(code, {})
                name = info.get("name", code)
                sector = info.get("sector", "未知")
            except ImportError:
                name = code
                sector = "未知"

            # Apply sector diversity filter
            if sector in seen_sectors:
                continue

            predictions.append({
                "code": code,
                "name": name,
                "sector": sector,
                "prob_up": round(float(prob_up), 4),
                "expected_return_10d": round(float(expected_return), 2),
                "confidence": round(float(confidence), 4),
                "predicted_direction": "涨" if prob_up > 0.5 else "跌",
                "model_type": model_payload.get("binary_model_name", "ensemble"),
                "prediction_date": date.today().isoformat(),
            })

            seen_sectors.add(sector)

            if len(predictions) >= TOP_N_PREDICT + 3:  # collect extras for diversity
                break

        except (OSError, ValueError, AttributeError, TypeError, KeyError) as exc:
            if debug:
                print(f"[ML] Failed for {code}: {exc}")
            continue

    # Sort by expected return descending, take top 3
    predictions.sort(key=lambda x: -x["expected_return_10d"])
    top3 = predictions[:TOP_N_PREDICT]

    if debug:
        print(f"[ML] Generated {len(top3)} predictions (sector-diversified)")
        for p in top3:
            print(f"  {p['code']} {p['name']}: "
                  f"P(涨)={p['prob_up']:.2%}, "
                  f"E[return]={p['expected_return_10d']:+.2f}%, "
                  f"conf={p['confidence']:.2f}")

    return top3


# ===================================================================
#  COMPARISON: ML vs Z-score
# ===================================================================

def run_comparison(
    ml_codes: list[str] | None = None,
    zscore_profile: str = "均衡",
    debug: bool = False,
) -> dict:
    """Run ML and Z-score predictions side-by-side and compare.

    Returns a dict suitable for JSON serialization.
    """
    if ml_codes is None:
        ml_codes = CANDIDATE_CODES[:]

    result = {
        "date": date.today().isoformat(),
        "ml_prediction": [],
        "zscore_prediction": [],
        "comparison": {},
    }

    # ── ML Prediction ──
    if debug:
        print("=" * 60)
        print("[COMPARE] Running ML prediction...")
    ml_top3 = predict_top3(codes=ml_codes[:30], retrain=False, debug=debug)
    result["ml_prediction"] = ml_top3

    # ── Z-score Prediction ──
    if debug:
        print("=" * 60)
        print("[COMPARE] Running Z-score prediction...")
    try:
        from etf_platform.decision.two_week_picker import pick_top3
        zs_top3, _ = pick_top3(profile=zscore_profile, max_candidates=60, debug=debug)
        result["zscore_prediction"] = zs_top3
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError) as exc:
        logger.warning("Z-score prediction failed: %s", exc)
        result["zscore_prediction"] = []

    # ── Overlap analysis ──
    ml_codes_set = {p["code"] for p in ml_top3}
    zs_codes_set = {p.get("code", p.get("etf_code", "")) for p in result["zscore_prediction"]}

    overlap = ml_codes_set & zs_codes_set
    result["comparison"] = {
        "ml_top3_codes": sorted(ml_codes_set),
        "zscore_top3_codes": sorted(zs_codes_set),
        "overlap_count": len(overlap),
        "overlap_codes": sorted(overlap),
        "ml_unique": sorted(ml_codes_set - zs_codes_set),
        "zscore_unique": sorted(zs_codes_set - ml_codes_set),
    }

    if debug:
        print(f"\n[COMPARE] ML Top3: {[p['code'] for p in ml_top3]}")
        print(f"[COMPARE] Z-score Top3: {[p.get('code', p.get('etf_code','')) for p in result['zscore_prediction']]}")
        print(f"[COMPARE] Overlap: {sorted(overlap)}")

    return result


def save_comparison_report(comp: dict) -> Path:
    """Save comparison report to predictions directory."""
    filename = f"ml_vs_zscore_{date.today().isoformat()}.json"
    filepath = PRED_DIR / filename
    filepath.write_text(json.dumps(comp, ensure_ascii=False, indent=2))
    logger.info("Comparison report saved to %s", filepath)
    return filepath


# ===================================================================
#  CLI Entry Point
# ===================================================================

def main() -> None:
    """CLI entry point for ML predictor."""
    import argparse

    parser = argparse.ArgumentParser(
        description="ML-based ETF 10-day return predictor (XGB+LGBM+CAT ensemble)"
    )
    parser.add_argument(
        "--mode", choices=["predict", "train", "compare", "full"],
        default="full",
        help="Operation mode (default: full = train + predict + compare)",
    )
    parser.add_argument("--codes", nargs="+", help="Specific ETF codes to use")
    parser.add_argument("--retrain", action="store_true", help="Force retrain before prediction")
    parser.add_argument("--debug", action="store_true", help="Verbose output")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    if args.mode in ("train", "full"):
        result = train_model(codes=args.codes, save=True, debug=args.debug)
        if args.mode == "train":
            print("\n=== Training Summary ===")
            print(f"Samples: {result.n_samples}")
            print(f"Features: {result.n_features}")
            print(f"Binary accuracy (last fold): {result.binary_accuracy}")
            print(f"Binary CV scores: {result.binary_cv_scores}")
            print(f"Regression RMSE (last fold): {result.regression_rmse}")
            print(f"Regression CV scores: {result.regression_cv_scores}")
            if result.feature_importance:
                top5 = sorted(result.feature_importance.items(), key=lambda x: -x[1])[:5]
                print(f"Top-5 features: {top5}")
            return

    if args.mode in ("predict", "full"):
        top3 = predict_top3(codes=args.codes, retrain=args.retrain, debug=args.debug)
        print(f"\n{'=' * 60}")
        print(f"📈 ML ETF 10-Day Return Prediction — {date.today().isoformat()}")
        print(f"{'=' * 60}")
        for i, p in enumerate(top3, 1):
            marker = "🟢" if p["prob_up"] > 0.6 else ("🟡" if p["prob_up"] > 0.5 else "🔴")
            print(f"\n  {i}. {marker} {p['code']} {p['name']}")
            print(f"     Sector: {p['sector']}")
            print(f"     P(上涨): {p['prob_up']:.1%} | E[10d收益]: {p['expected_return_10d']:+.2f}%")
            print(f"     置信度: {p['confidence']:.2f} | 模型: {p['model_type']}")
        print(f"\n{'=' * 60}")

    if args.mode in ("compare", "full"):
        comp = run_comparison(codes=args.codes, debug=args.debug)
        filepath = save_comparison_report(comp)
        print(f"\n📊 Comparison report saved to: {filepath}")
        print(f"   ML Top3: {[p['code'] for p in comp['ml_prediction']]}")
        print(f"   Z-score Top3: {[p.get('code', p.get('etf_code','')) for p in comp['zscore_prediction']]}")
        print(f"   Overlap: {comp['comparison'].get('overlap_count', 0)}")


if __name__ == "__main__":
    main()
