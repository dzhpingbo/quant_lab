import akshare as ak
import time

print("测试 akshare ETF 接口...")
t0 = time.time()
try:
    df = ak.fund_etf_spot_em()
    print(f"成功! 获取 {len(df)} 只ETF, 耗时 {time.time()-t0:.1f}s")
    print("列名:", list(df.columns))
    print("前3行:")
    print(df.head(3).to_string())
except Exception as e:
    print(f"失败: {e}")
