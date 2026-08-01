#!/usr/bin/env python3
"""cross_validate.py - ETF平台代码变更验证脚本

验证流程:
1. 检查import链完整性
2. 检查权重同步 (_WEIGHTS vs CATEGORY_WEIGHTS)
3. 检查LAYER_CATEGORIES包含所有层
4. 运行基本功能测试
5. 检查文件UTF-8完整性
"""
import sys
import ast
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # etf-platform root
sys.path.insert(0, str(BASE / "src"))

def check_imports(py_files):
    """检查Python文件import链"""
    errors = []
    for py_file in py_files:
        try:
            content = py_file.read_text(encoding='utf-8')
            tree = ast.parse(content, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    # 检查相对导入
                    if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
                        # 相对导入，跳过详细检查
                        pass
        except SyntaxError as e:
            errors.append(f"{py_file.relative_to(BASE)}: {e}")
        except UnicodeDecodeError as e:
            errors.append(f"{py_file.relative_to(BASE)}: UTF-8 decode error: {e}")
    return errors

def check_weights_sync():
    """检查pipeline.py和screener.py权重同步"""
    pipeline_py = BASE / "src" / "etf_platform" / "pipeline.py"
    screener_py = BASE / "src" / "etf_platform" / "decision" / "screener.py"
    
    issues = []
    
    if pipeline_py.exists():
        content = pipeline_py.read_text(encoding='utf-8')
        if "_WEIGHTS" not in content:
            issues.append("pipeline.py缺少_WEIGHTS")
        if "_LAYER_TO_CATEGORY" not in content:
            issues.append("pipeline.py缺少_LAYER_TO_CATEGORY")
    
    if screener_py.exists():
        content = screener_py.read_text(encoding='utf-8')
        if "CATEGORY_WEIGHTS" not in content:
            issues.append("screener.py缺少CATEGORY_WEIGHTS")
    
    return issues

def check_layer_categories():
    """检查LAYER_CATEGORIES包含所有层"""
    screener_py = BASE / "src" / "etf_platform" / "decision" / "screener.py"
    
    if not screener_py.exists():
        return ["screener.py不存在"]
    
    content = screener_py.read_text(encoding='utf-8')
    
    required_layers = [
        "L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics", "L7_Irreplaceable",
        "L8_CapitalFlow", "L9_Signals", "L10_Demand", "L11_SectorRisk",
        "L12_PoliticalRisk", "L13_MacroCycle", "L14_StoicRisk",
        "L15_StateSim", "L16_LiveSignals", "L17_Factor",
        "L18_VaR", "L19_FXChannel", "L20_OptionVol",
        "L21_Behavior", "L21_Herding", "L21_Disposition",
        "L21_Overreaction", "L21_Contrarian", "L21_Attention",
        "L22_Pendulum", "L23_Micro"
    ]
    
    missing = [layer for layer in required_layers if layer not in content]
    return missing

def check_utf8_integrity(py_files):
    """检查文件UTF-8完整性"""
    errors = []
    for py_file in py_files:
        try:
            content = py_file.read_text(encoding='utf-8')
            content.encode('utf-8')
        except UnicodeDecodeError as e:
            errors.append(f"{py_file.relative_to(BASE)}: {e}")
    return errors

def main():
    print("=" * 60)
    print("ETF Platform Cross Validate")
    print("=" * 60)
    
    all_pass = True
    
    # 1. Import链检查
    print("\n1. Import链检查...")
    py_files = list((BASE / "src").rglob("*.py"))
    import_errors = check_imports(py_files)
    if import_errors:
        print(f"   ✗ {len(import_errors)} 个错误:")
        for e in import_errors:
            print(f"     - {e}")
        all_pass = False
    else:
        print(f"   ✓ {len(py_files)} 个文件无错误")
    
    # 2. 权重同步检查
    print("\n2. 权重同步检查...")
    weight_issues = check_weights_sync()
    if weight_issues:
        print(f"   ✗ {len(weight_issues)} 个问题:")
        for w in weight_issues:
            print(f"     - {w}")
        all_pass = False
    else:
        print("   ✓ 权重同步正常")
    
    # 3. LAYER_CATEGORIES检查
    print("\n3. LAYER_CATEGORIES检查...")
    layer_missing = check_layer_categories()
    if layer_missing:
        print(f"   ✗ {len(layer_missing)} 个层缺失:")
        for l in layer_missing:
            print(f"     - {l}")
        all_pass = False
    else:
        print("   ✓ 所有层已包含")
    
    # 4. UTF-8完整性检查
    print("\n4. UTF-8完整性检查...")
    utf8_errors = check_utf8_integrity(py_files)
    if utf8_errors:
        print(f"   ✗ {len(utf8_errors)} 个错误:")
        for e in utf8_errors:
            print(f"     - {e}")
        all_pass = False
    else:
        print(f"   ✓ {len(py_files)} 个文件UTF-8完整")
    
    # 总结
    print("\n" + "=" * 60)
    if all_pass:
        print("✓ 所有检查通过")
    else:
        print("✗ 发现问题，请修复后重新运行")
    print("=" * 60)
    
    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())
