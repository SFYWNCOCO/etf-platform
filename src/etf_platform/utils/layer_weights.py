"""Composite 层权重加载: 读 config/weights.yaml 的 composite_layer_weights 块。

缺文件 / enabled!=true / 字段异常 → 返回 None（pipeline 保持纯等权原行为, loud 日志）。
正常 → 返回 {layer_key: weight}（仅 overrides; 未覆盖层由调用方用 default=1.0 补齐）。
"""
import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
_DEFAULT_WEIGHTS_FILE = _CONFIG_DIR / "weights.yaml"


def load_composite_layer_weights(path: Optional[str] = None) -> Optional[dict]:
    """返回 composite 层权重映射 {layer: weight}; 未启用/异常返回 None(=纯等权原行为)。"""
    yaml_path = Path(path) if path else _DEFAULT_WEIGHTS_FILE
    if not yaml_path.exists():
        logger.warning("[layer_weights] 配置文件不存在: %s, composite 保持等权", yaml_path)
        return None
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.warning("[layer_weights] 读取/解析失败 %s: %s, composite 保持等权", yaml_path, e)
        return None
    if not isinstance(data, dict):
        logger.warning("[layer_weights] 配置结构异常(非 dict): %s, composite 保持等权", yaml_path)
        return None
    block = data.get("composite_layer_weights")
    if not isinstance(block, dict):
        logger.warning("[layer_weights] 缺少 composite_layer_weights 块: %s, composite 保持等权", yaml_path)
        return None
    if block.get("enabled") is not True:
        logger.warning("[layer_weights] enabled!=true, composite 保持等权")
        return None
    default_w = block.get("default", 1.0)
    if not isinstance(default_w, (int, float)) or default_w <= 0:
        logger.warning("[layer_weights] default 字段异常(%r), composite 保持等权", default_w)
        return None
    overrides = block.get("overrides")
    if not isinstance(overrides, dict):
        logger.warning("[layer_weights] overrides 字段异常, composite 保持等权")
        return None
    out: dict = {}
    for k, v in overrides.items():
        if isinstance(v, (int, float)) and v > 0:
            out[str(k)] = float(v)
        else:
            logger.warning("[layer_weights] 忽略非法权重 %s=%r", k, v)
    if not out:
        logger.warning("[layer_weights] overrides 无有效权重, composite 保持等权")
        return None
    logger.info("[layer_weights] 已加载 %d 个 composite 层权重: %s", len(out), out)
    return out
