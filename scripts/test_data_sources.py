"""
测试多种财务数据获取方式:
1. 雪球移动端API (token-free)
2. baostock 财务接口
3. akshare 财务接口（非新浪）
4. 东方财富财务接口
"""
import sys, warnings, os
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(encoding='utf-8')
import requests, json

os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

print("=" * 60)
print("测试1: 雪球 xq_a_token 通过API获取")
print("=" * 60)
# 雪球提供了一个公开的 token 接口
session = requests.Session()
session.verify = False
session.trust_env = False
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0) Chrome/124'})

try:
    # 方法1: 通过雪球token接口
    r = session.get('https://xueqiu.com/service/v5/stock/realtime/quotec?symbol=SH000001', timeout=8)
    print(f"  service接口: {r.status_code}")
except Exception as e:
    print(f"  service失败: {e}")

try:
    # 方法2: 雪球stock API通过公开token
    r2 = session.get('https://api.xueqiu.com/snow/followstock/stocks/count.json', timeout=8)
    print(f"  api接口: {r2.status_code}, cookies: {dict(session.cookies)}")
except Exception as e:
    print(f"  api失败: {e}")

print()
print("=" * 60)
print("测试2: baostock 财务数据")
print("=" * 60)
try:
    import baostock as bs
    lg = bs.login()
    print(f"  baostock登录: {lg.error_code} - {lg.error_msg}")
    if lg.error_code == '0':
        # 查询盈利能力
        rs = bs.query_profit_data(code='sh.600000', year=2023, quarter=4)
        print(f"  盈利数据字段: {rs.fields}")
        data = []
        while rs.error_code == '0' and rs.next():
            data.append(rs.get_row_data())
        print(f"  数据: {data[:2]}")
        bs.logout()
except Exception as e:
    print(f"  baostock失败: {e}")

print()
print("=" * 60)
print("测试3: akshare 财务数据（东方财富）")
print("=" * 60)
try:
    import akshare as ak
    
    # 财务摘要（东方财富）
    df_fin = ak.stock_financial_abstract_ths(symbol='600000', indicator='按年度')
    print(f"  同花顺财务摘要: {df_fin.shape}")
    print(f"  列: {df_fin.columns.tolist()}")
    print(f"  最新: {df_fin.head(2).to_string()}")
except Exception as e:
    print(f"  同花顺财务失败: {e}")

try:
    import akshare as ak
    # 东方财富财务指标
    df_ind = ak.stock_financial_analysis_indicator_lg(symbol='600000')
    print(f"\n  东财财务指标: {df_ind.shape}")
    print(f"  列: {df_ind.columns.tolist()[:10]}")
except Exception as e:
    print(f"  东财财务失败: {e}")

print()
print("=" * 60)
print("测试4: 东方财富个股PE/PB实时")
print("=" * 60)
try:
    import akshare as ak
    df_val = ak.stock_a_pe_and_pb()
    print(f"  PE/PB数据: {df_val.shape}")
    print(f"  列: {df_val.columns.tolist()}")
    row = df_val[df_val['代码'] == '600000'] if '代码' in df_val.columns else df_val.head(2)
    print(f"  600000: {row.to_string()}")
except Exception as e:
    print(f"  PE/PB失败: {e}")
