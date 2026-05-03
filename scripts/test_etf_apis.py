import akshare as ak
import time

print("Test Sina ETF hist API...")
try:
    t0 = time.time()
    df = ak.fund_etf_hist_sina(symbol="sh510300")
    print(f"Sina OK: {len(df)} rows in {time.time()-t0:.1f}s")
    print(df.head(3).to_string())
except Exception as e:
    print(f"Sina fail: {e}")

print("\nTest Tencent ETF hist API...")
try:
    t0 = time.time()
    df = ak.fund_etf_hist_ths(symbol="510300", indicator="单位净值累计净值")
    print(f"THS OK: {len(df)} rows in {time.time()-t0:.1f}s")
    print(df.head(3).to_string())
except Exception as e:
    print(f"THS fail: {e}")

print("\nTest fund public basic...")
try:
    t0 = time.time()
    df = ak.fund_individual_basic_info_xq(symbol="510300")
    print(f"Xueqiu OK: {len(df)} rows in {time.time()-t0:.1f}s")
    print(df.head(3).to_string())
except Exception as e:
    print(f"Xueqiu fail: {e}")
