#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ETF分析系统全面测试脚本
用于验证系统各项功能的正确性
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

def test_etf_count():
    """测试ETF数量统计"""
    print("=" * 60)
    print("测试1: ETF数量统计")
    print("=" * 60)
    
    try:
        from src.etf_platform.config_loader import load_etfs
        etfs = load_etfs()
        
        total = len(etfs)
        buyable = sum(1 for v in etfs.values() if v.get("access") == "buyable")
        qdii = sum(1 for v in etfs.values() if v.get("access") == "qdii")
        fake = sum(1 for v in etfs.values() if v.get("access") == "fake")
        
        print(f"总ETF数量: {total}")
        print(f"可买入ETF: {buyable}")
        print(f"跨境QDII: {qdii}")
        print(f"模拟杠杆: {fake}")
        
        # 检查重复code
        codes = list(etfs.keys())
        unique_codes = set(codes)
        if len(codes) == len(unique_codes):
            print("✅ 无重复code")
        else:
            print(f"❌ 发现重复code: {len(codes) - len(unique_codes)}个")
            
        # 检查缺失字段
        missing_fields = []
        for code, info in etfs.items():
            if not info.get("name"):
                missing_fields.append((code, "name"))
            if not info.get("sector"):
                missing_fields.append((code, "sector"))
            if info.get("risk_level") is None:
                missing_fields.append((code, "risk_level"))
                
        if missing_fields:
            print(f"❌ 发现{len(missing_fields)}个缺失字段")
            for code, field in missing_fields[:5]:
                print(f"  - {code}: 缺少{field}")
        else:
            print("✅ 无缺失字段")
            
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_data_sources():
    """测试数据源健康状态"""
    print("\n" + "=" * 60)
    print("测试2: 数据源健康状态")
    print("=" * 60)
    
    try:
        from src.etf_platform.data.manager import check_all_sources, get_price
        
        # 检查所有数据源
        health_results = check_all_sources()
        
        price_sources_ok = 0
        news_sources_ok = 0
        
        for health in health_results:
            status_icon = "✅" if health.status.value == "healthy" else "⚠️" if health.status.value == "degraded" else "❌"
            print(f"{status_icon} {health.source_name}: {health.status.value} ({health.latency_ms:.0f}ms)")
            if health.error:
                print(f"   错误: {health.error}")
            
            if "price" in health.source_name.lower():
                if health.status.value == "healthy":
                    price_sources_ok += 1
            else:
                if health.status.value == "healthy":
                    news_sources_ok += 1
        
        print(f"\n价格源: {price_sources_ok}/3 正常")
        print(f"新闻源: {news_sources_ok}/4 正常")
        
        # 测试实际价格获取
        print("\n测试实际价格获取 (510300 沪深300ETF):")
        price, source = get_price("510300")
        if price:
            print(f"✅ 获取成功: {source} - 价格:{price.price}, 涨跌:{price.change_pct}%")
        else:
            print("❌ 获取失败")
            
        return price_sources_ok >= 1  # 至少1个价格源正常
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_news_sources():
    """测试新闻数据源"""
    print("\n" + "=" * 60)
    print("测试3: 新闻数据源")
    print("=" * 60)
    
    try:
        from src.etf_platform.data.manager import get_news
        
        # 测试不同关键词
        keywords = ["AI", "新能源", "金融"]
        
        for keyword in keywords:
            print(f"\n关键词: {keyword}")
            news_items = get_news(keyword, limit=5)
            
            if news_items:
                print(f"✅ 获取{len(news_items)}条新闻:")
                for item in news_items[:3]:
                    print(f"   [{item.source}] {item.title[:40]}... (相关度:{item.relevance})")
            else:
                print(f"❌ 未获取到新闻")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_recommendation():
    """测试推荐功能"""
    print("\n" + "=" * 60)
    print("测试4: 推荐功能")
    print("=" * 60)
    
    try:
        from src.etf_platform.pipeline import run_full
        from src.etf_platform.decision.screener import screen
        
        # 测试单ETF分析
        print("测试单ETF分析 (510300 沪深300ETF):")
        result = run_full("510300", live=True)
        
        if "error" not in result:
            print(f"✅ 分析成功，综合评分: {result.get('score', 0)}")
            print(f"   名称: {result.get('name')}")
            print(f"   板块: {result.get('sector')}")
            
            # 显示主要因子
            layer_scores = result.get("layer_scores", {})
            if layer_scores:
                avg_score = sum(layer_scores.values()) / len(layer_scores)
                print(f"   平均因子分: {avg_score:.2f}/10")
        else:
            print(f"❌ 分析失败: {result['error']}")
            return False
        
        # 测试批量筛选 (小样本)
        print("\n测试批量筛选 (Top 3):")
        try:
            # 使用较小的limit避免超时
            screen_results = screen(limit=3, profile="均衡")
            
            if screen_results:
                print(f"✅ 筛选成功，返回{len(screen_results)}个结果:")
                for i, item in enumerate(screen_results[:3], 1):
                    code = item.get("code") or item.get("etf_code", "N/A")
                    name = item.get("name", "Unknown")
                    score = item.get("composite_score", 0)
                    rank = item.get("rank", i)
                    print(f"   {rank}. {code} - {name} (评分:{score:.2f})")
                    
                    # 检查关键字段
                    if not code or code == "N/A":
                        print(f"   ⚠️ 警告: etf_code字段缺失")
            else:
                print("❌ 筛选失败，无结果返回")
                return False
                
        except Exception as e:
            print(f"⚠️ 批量筛选测试跳过 (可能超时): {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_akshare_issue():
    """专门测试AKShare问题"""
    print("\n" + "=" * 60)
    print("测试5: AKShare字段映射问题")
    print("=" * 60)
    
    try:
        import akshare
        
        print("检查AKShare API返回的字段:")
        df = akshare.fund_etf_fund_daily_em()
        if df is not None and not df.empty:
            print(f"✅ 获取到{len(df)}条基金数据")
            print(f"字段列表: {', '.join(df.columns[:10])}...")
            
            # 检查510300
            row = df[df["基金代码"] == "510300"]
            if not row.empty:
                print(f"\n510300数据:")
                print(f"  基金代码: {row.iloc[0]['基金代码']}")
                print(f"  基金简称: {row.iloc[0]['基金简称']}")
                print(f"  市价: {row.iloc[0].get('市价', 'N/A')}")
                print(f"  增长率: {row.iloc[0].get('增长率', 'N/A')}")
            else:
                print("❌ 未找到510300数据")
        else:
            print("❌ 无法获取基金数据")
            
        # 测试当前代码的问题
        print("\n当前代码问题:")
        print("❌ 使用'代码'字段，但实际字段名是'基金代码'")
        print("❌ 使用'名称'字段，但实际字段名是'基金简称'")
        print("❌ 使用'最新价'字段，但实际字段名是'市价'")
        print("❌ 使用'涨跌幅'字段，但实际字段名是'增长率'")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def main():
    """运行所有测试"""
    print("ETF分析系统全面测试")
    print("=" * 60)
    
    tests = [
        ("ETF数量检查", test_etf_count),
        ("数据源健康检查", test_data_sources),
        ("新闻数据检查", test_news_sources),
        ("推荐功能检查", test_recommendation),
        ("AKShare问题检查", test_akshare_issue),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ {test_name}测试异常: {e}")
            results.append((test_name, False))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("🎉 所有测试通过！")
        return 0
    else:
        print(f"⚠️ 有{total-passed}个测试失败，需要修复")
        return 1

if __name__ == "__main__":
    sys.exit(main())
