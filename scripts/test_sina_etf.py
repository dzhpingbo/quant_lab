import akshare as ak
import time

tests = [
    ("sh510050", "SSE50 ETF"),
    ("sh510500", "CSI500 ETF"),
    ("sh588050", "STAR50 ETF"),
    ("sz159915", "GEM ETF"),
    ("sh512660", "Military ETF"),
    ("sh518880", "Gold ETF"),
]

for sym, name in tests:
    try:
        t0 = time.time()
        df = ak.fund_etf_hist_sina(symbol=sym)
        rows = len(df)
        start = df['date'].min() if 'date' in df.columns else '?'
        elapsed = time.time() - t0
        years = rows / 244
        print(f"OK   {sym} {name:<20} {rows:>5} rows ~{years:.1f}y from {start} ({elapsed:.1f}s)")
    except Exception as e:
        print(f"FAIL {sym} {name:<20} {str(e)[:60]}")
    time.sleep(1)
