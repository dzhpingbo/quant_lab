"""检查失败股票原因 + 补充下载"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
os.environ['HTTP_PROXY']  = 'http://127.0.0.1:7897'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7897'

import yfinance as yf
import pandas as pd
from pathlib import Path

# 检查几只知名大股为何批量下载失败
print("=== 单只重试失败股票 ===")
check = ['600000.SS', '600036.SS', '600519.SS', '601318.SS', '600016.SS']
save_dir = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/SH")

recovered = 0
for c in check:
    t = yf.Ticker(c)
    df = t.history(start='2010-01-01', end='2026-04-08', timeout=20)
    rows = len(df)
    status = "OK" if rows > 100 else "EMPTY"
    print(f"  {c}: {rows}行 [{status}]")
    if rows > 100:
        num = c.split('.')[0]
        fp  = save_dir / f"{num}.SH.csv"
        df.index.name = 'date'
        df.columns    = [col.lower() for col in df.columns]
        df.to_csv(fp, encoding='utf-8')
        print(f"    -> 已保存: {fp}")
        recovered += 1

print(f"\n单只重试恢复: {recovered} 只")
