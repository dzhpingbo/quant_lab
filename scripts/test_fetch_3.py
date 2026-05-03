"""快速测试：并行抓取3只股票"""
import sys, os, time, datetime, warnings, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings("ignore")

YF_SH = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/SH")
YF_SZ = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/SZ")
START = time.time()

def log(msg=""):
    elapsed = time.time() - START
    print(f"[{elapsed:.0f}s] {msg}", flush=True)

def sf(v):
    try:
        f = float(v)
        return None if f != f else f
    except:
        return None

def pf(v):
    if v is None:
        return None
    try:
        f = float(v)
        return round(f * 100, 4) if abs(f) < 1 else f
    except:
        return None

# 加载候选
log("Loading pool...")
fp = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/因子数据库/七类池子筛选结果.xlsx")
codes = []
if fp.exists():
    dfp = pd.read_excel(fp, sheet_name="全部池子")
    codes = dfp["代码"].dropna().astype(str).str.zfill(6).tolist()

test_codes = codes[:3]
log(f"Test codes: {test_codes}")

def fetch_one(sym):
    import baostock as bs

    lg = bs.login()
    if lg.error_code != "0":
        return {"code": sym, "ok": False, "error": lg.error_msg}

    bs_sym = f"sh.{sym}" if sym.startswith(("6", "5", "9")) else f"sz.{sym}"
    records = []
    today = datetime.date.today()

    for year in range(today.year, today.year - 3, -1):
        for q in [4, 3, 2, 1]:
            rs = bs.query_profit_data(code=bs_sym, year=year, quarter=q)
            while rs.error_code == "0" and rs.next():
                row = rs.get_row_data()
                d = dict(zip(rs.fields, row))
                records.append({
                    "report_date": d.get("statDate"),
                    "roe": pf(d.get("roeAvg")),
                    "net_margin": pf(d.get("npMargin")),
                    "gross_margin": pf(d.get("gpMargin")),
                    "eps": sf(d.get("epsTTM")),
                })
            if len(records) >= 4:
                break
        if len(records) >= 4:
            break

    bs.logout()

    # K线
    kline = pd.DataFrame()
    for cdir in [YF_SH, YF_SZ]:
        p = cdir / f"{sym}.SS.csv"
        if not p.exists():
            p = cdir / f"{sym}.SZ.csv"
        if p.exists():
            try:
                df = pd.read_csv(p, parse_dates=["Date"], nrows=200)
                kline = df
            except Exception:
                pass
            break

    return {
        "code": sym,
        "financial": pd.DataFrame(records[:4]),
        "kline": kline,
        "ok": True,
    }

log("Start fetching with 3 workers...")
t0 = time.time()

results = {}
with ThreadPoolExecutor(max_workers=3) as ex:
    futures = {ex.submit(fetch_one, c): c for c in test_codes}
    for f in as_completed(futures):
        c = futures[f]
        try:
            r = f.result()
            results[c] = r
            fin = r.get("financial", pd.DataFrame())
            kln = r.get("kline", pd.DataFrame())
            log(f"Done: {c} | Fin={len(fin)} rows | Kln={len(kln)} rows | OK={r.get('ok')}")
        except Exception as e:
            log(f"Error {c}: {e}")
            results[c] = {"code": c, "ok": False, "error": str(e)}

log(f"Total time: {time.time()-t0:.1f}s")
log("Done!")
print()

# 显示结果
for c, r in results.items():
    fin = r.get("financial", pd.DataFrame())
    if len(fin) > 0:
        roe = fin["roe"].iloc[0] if "roe" in fin.columns else None
        nm = fin["net_margin"].iloc[0] if "net_margin" in fin.columns else None
        gm = fin["gross_margin"].iloc[0] if "gross_margin" in fin.columns else None
        print(f"  {c}: ROE={roe:.1f}% | 净利率={nm:.1f}% | 毛利率={gm:.1f}%")
    else:
        print(f"  {c}: No data")
