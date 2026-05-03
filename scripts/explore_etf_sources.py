#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
探索可用的ETF数据源，找到最全的ETF列表
"""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import akshare as ak
import pandas as pd

results = {}

# --- 方法1: 东方财富ETF列表（但不用东财下载历史） ---
print("=== [1] fund_etf_spot_em (东方财富实时行情) ===")
try:
    t0 = time.time()
    df = ak.fund_etf_spot_em()
    print(f"  OK: {len(df)}只 | 耗时{time.time()-t0:.1f}s")
    print(f"  列: {df.columns.tolist()}")
    # 看代码列名
    code_col = [c for c in df.columns if '代码' in c or 'code' in c.lower()]
    name_col = [c for c in df.columns if '名称' in c or 'name' in c.lower()]
    print(f"  代码列: {code_col}, 名称列: {name_col}")
    if code_col:
        print(df[code_col[0]].head(5).tolist())
    results['em'] = df
except Exception as e:
    print(f"  FAIL: {e}")

print()

# --- 方法2: 新浪ETF列表 ---
print("=== [2] fund_etf_category_sina (新浪ETF列表) ===")
try:
    t0 = time.time()
    df2 = ak.fund_etf_category_sina(symbol="ETF基金")
    print(f"  OK: {len(df2)}只 | 耗时{time.time()-t0:.1f}s")
    print(f"  列: {df2.columns.tolist()}")
    print(df2.head(3).to_string())
    results['sina'] = df2
except Exception as e:
    print(f"  FAIL: {e}")

print()

# --- 方法3: 看yfinance能否识别ETF ---
print("=== [3] yfinance ETF测试 ===")
import os
os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7897'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7897'
try:
    import yfinance as yf
    # ETF在Yahoo的格式也是 510300.SS 或 159915.SZ
    test_etfs = [
        ('510050.SS', '50ETF沪'),
        ('510300.SS', '300ETF沪'),
        ('159915.SZ', '创业板ETF'),
        ('510500.SS', '中证500ETF'),
        ('512880.SS', '证券ETF'),
        ('515050.SS', '科技ETF'),
        ('513050.SS', '中概互联'),
        ('159941.SZ', '纳指ETF'),
    ]
    for code, name in test_etfs:
        try:
            t = yf.Ticker(code)
            df_yf = t.history(start='2010-01-01', end='2026-04-09', timeout=10)
            if len(df_yf) > 0:
                print(f"  ✓ {code} {name}: {len(df_yf)}行 | {df_yf.index.min().date()}~{df_yf.index.max().date()}")
            else:
                print(f"  ✗ {code} {name}: 无数据")
        except Exception as e:
            print(f"  ✗ {code} {name}: {e}")
except Exception as e:
    print(f"  yfinance FAIL: {e}")

# --- 汇总 ---
print()
print("=== 汇总 ===")
for k, v in results.items():
    print(f"  {k}: {len(v)}只ETF")
