"""诊断K线因子计算"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import pandas as pd
import numpy as np

def _safe_ret(closes, period):
    if len(closes) < period: return None
    try: return (closes[-1] / closes[-period]) - 1
    except: return None

# 测试 000786
p = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/SZ/000786.SZ.csv")
df = pd.read_csv(p, parse_dates=["Date"])
df.columns = [c.lower() for c in df.columns]
if "date" not in df.columns:
    df = df.rename(columns={"Date": "date"})
print(f"000786: {len(df)} rows | cols={df.columns.tolist()}")
print(df[["date","close","volume"]].tail(3).to_string())

closes = df["close"].values
print(f"\nret_5d={_safe_ret(closes,5):.4f}")
print(f"ret_20d={_safe_ret(closes,20):.4f}")
print(f"ret_60d={_safe_ret(closes,60):.4f}")
print(f"ret_120d={_safe_ret(closes,120):.4f}")
