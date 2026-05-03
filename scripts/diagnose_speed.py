"""
诊断：fundamental_fetcher 速度瓶颈
"""
import sys, time, os
sys.stdout.reconfigure(encoding='utf-8')

t0 = time.time()

# 1. 测试 baostock 登录（已知 ~5秒）
import baostock as bs
t1 = time.time()
lg = bs.login()
print(f"[1] baostock登录: {lg.error_code} | 耗时 {t1-t0:.1f}s")
bs.logout()

# 2. 测试 baostock 单季度查询
t2 = time.time()
lg = bs.login()
rs = bs.query_profit_data('sh.600000', 2024, 4)
rows = []
while rs.next() and rs.error_code == '0':
    rows.append(rs.get_row_data())
bs.logout()
print(f"[2] baostock单季度查询: {len(rows)}行 | 耗时 {time.time()-t2:.1f}s")

# 3. 测试 akshare THS
t3 = time.time()
import akshare as ak
df = ak.stock_financial_abstract_ths('600000', '按年度')
print(f"[3] akshare THS年报: {df.shape} | 耗时 {time.time()-t3:.1f}s")

# 4. 速度估算
per_stock_bs = (t1-t0) + (time.time()-t2)  # baostock每只
per_stock_ak = time.time()-t3               # akshare每只
total_per_stock = per_stock_bs + per_stock_ak

print(f"\n=== 速度估算 ===")
print(f"每只股票: baostock ~{per_stock_bs:.1f}s + akshare ~{per_stock_ak:.1f}s = ~{total_per_stock:.1f}s")
print(f"100只股票: ~{total_per_stock*100/60:.0f}分钟")
print(f"1000只: ~{total_per_stock*1000/60:.0f}分钟")
print(f"3000只: ~{total_per_stock*3000/60:.0f}分钟")
