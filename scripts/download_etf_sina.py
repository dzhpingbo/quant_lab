"""
ETF数据下载 - 新浪财经接口（稳定可用版）
全部ETF均通过新浪接口获取，每只请求间隔2秒，全程心跳
"""
import akshare as ak
import pandas as pd
import time
import json
import random
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/ETF")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DELAY = 2.0  # 每次请求间隔
MAX_RETRIES = 3
BATCH_WAIT = 10
HEARTBEAT = 60

# 完整ETF清单（按新浪格式：sh=上交所，sz=深交所）
ETF_LIST = [
    # ===== 宽基ETF - 10年以上 =====
    ("sh510050", "510050", "SSE50 ETF"),
    ("sh510300", "510300", "CSI300 ETF"),
    ("sh510500", "510500", "CSI500 ETF"),
    ("sh510100", "510100", "SSE100 ETF"),
    ("sh510180", "510180", "SSE180 ETF"),
    ("sh510880", "510880", "CSI Dividend ETF"),
    ("sz159915", "159915", "GEM ETF"),
    ("sz159901", "159901", "SZ100 ETF"),
    ("sz159902", "159902", "SME ETF"),
    ("sz159903", "159903", "SZ Growth ETF"),
    ("sz159919", "159919", "CSI300 SZ ETF"),
    ("sz159922", "159922", "CSI500 SZ ETF"),
    ("sh510010", "510010", "SSE100 SZ-like ETF"),

    # ===== QDII ETF - 10年以上 =====
    ("sh510900", "510900", "HSCEI ETF"),
    ("sz159920", "159920", "HangSeng ETF"),

    # ===== 行业ETF - 10年以上 =====
    ("sh512880", "512880", "Securities Sector ETF"),
    ("sh518880", "518880", "Gold ETF"),
    ("sh512660", "512660", "Defense/Military ETF"),
    ("sh512010", "512010", "Healthcare ETF"),
    ("sh512000", "512000", "Securities Broad ETF"),
    ("sh512200", "512200", "RealEstate ETF"),
    ("sh512170", "512170", "Medical Equipment ETF"),

    # ===== 黄金/商品 =====
    ("sh518800", "518800", "Gold ETF EX"),
    ("sh159934", "159934", "Gold SZ ETF"),

    # ===== 科创/芯片 =====
    ("sh588000", "588000", "STAR50 ETF Huaxia"),
    ("sh588080", "588080", "STAR50 ETF EF"),
    ("sh588050", "588050", "STAR50 ETF Full"),
    ("sh512350", "512350", "CSI New Energy ETF"),
    ("sh512760", "512760", "Semiconductor ETF"),
    ("sh512800", "512800", "Banking Sector ETF"),
    ("sh512690", "512690", "Alcohol Sector ETF"),
    ("sh512380", "512380", "Medical Bio ETF"),

    # ===== QDII 纳斯达克/美股 =====
    ("sh513100", "513100", "Nasdaq100 ETF"),
    ("sh513500", "513500", "S&P500 ETF"),
    ("sz159941", "159941", "Nasdaq100 SZ ETF"),

    # ===== 债券ETF =====
    ("sh511010", "511010", "Bond ETF"),
    ("sh511260", "511260", "Treasury Bond ETF"),

    # ===== 中证系列 =====
    ("sh510110", "510110", "CSI 300 EqualWeight"),
    ("sh510120", "510120", "CSI 300 Value"),
]

# 已有文件列表（跳过）
existing = set()
for f in OUTPUT_DIR.glob("*.csv"):
    existing.add(f.stem)


def download_one(sina_code, std_code, name, retries=MAX_RETRIES):
    save_path = OUTPUT_DIR / f"{std_code}.SH.csv"
    if save_path.exists():
        return "exists", 0
    for r in range(retries):
        try:
            time.sleep(DELAY + random.uniform(0, 0.5))
            df = ak.fund_etf_hist_sina(symbol=sina_code)
            if df is None or len(df) < 50:
                return "no_data", 0
            # 标准化列名
            col_map = {}
            for c in df.columns:
                cs = str(c)
                if 'date' in cs.lower() or '日期' in cs:
                    col_map[c] = 'date'
                elif 'open' in cs.lower() or '开盘' in cs:
                    col_map[c] = 'open'
                elif 'close' in cs.lower() or '收盘' in cs:
                    col_map[c] = 'close'
                elif 'high' in cs.lower() or '最高' in cs:
                    col_map[c] = 'high'
                elif 'low' in cs.lower() or '最低' in cs:
                    col_map[c] = 'low'
                elif 'volume' in cs.lower() or '成交量' in cs:
                    col_map[c] = 'volume'
                elif 'amount' in cs.lower() or '成交额' in cs:
                    col_map[c] = 'amount'
            df = df.rename(columns=col_map)
            keep = [c for c in ['date','open','high','low','close','volume','amount'] if c in df.columns]
            df = df[keep]
            df.to_csv(save_path, index=False, encoding='utf-8')
            return "ok", len(df)
        except Exception as e:
            err = str(e)
            if r < retries - 1:
                time.sleep(5 * (r + 1))
            else:
                return f"fail:{err[:60]}", 0
    return "unknown", 0


print("=" * 60)
print("ETF Download - Sina Finance (Stable)")
print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Total: {len(ETF_LIST)} ETFs")
print(f"Existing skip: {len(existing)} files")
print("=" * 60)

success = []
already = []
failed = []
t0 = time.time()
last_hb = t0

for idx, (sina_code, std_code, name) in enumerate(ETF_LIST):
    if std_code in existing:
        already.append((std_code, name))
        continue

    status, rows = download_one(sina_code, std_code, name)
    if status == "ok":
        success.append((std_code, name, rows))
        years = rows / 244
        flag = "***10Y+" if rows > 2400 else ""
        print(f"[{idx+1:02d}/{len(ETF_LIST)}] {std_code} {name:<25} {rows:>5} rows ~{years:.1f}y {flag}")
    elif status == "exists":
        already.append((std_code, name))
    else:
        failed.append((std_code, name, status))
        print(f"[{idx+1:02d}/{len(ETF_LIST)}] {std_code} {name:<25} FAIL: {status}")

    # 心跳汇报
    now = time.time()
    if now - last_hb >= HEARTBEAT:
        elapsed = now - t0
        done = len(success) + len(already)
        rate = done / elapsed
        eta = (len(ETF_LIST) - done) / max(rate, 0.01)
        print(f"\n[HEARTBEAT {datetime.now().strftime('%H:%M:%S')}] "
              f"Done {done}/{len(ETF_LIST)} | "
              f"OK {len(success)} | Skip {len(already)} | Fail {len(failed)} | "
              f"Elapsed {elapsed/60:.1f}min | ETA {eta/60:.1f}min")
        last_hb = now

    # 批间休息
    if (idx + 1) % 15 == 0 and idx + 1 < len(ETF_LIST):
        print(f"  .. batch wait {BATCH_WAIT}s ..")
        time.sleep(BATCH_WAIT)

# 最终汇总
elapsed_total = time.time() - t0
ten_plus = [(c, n, r) for c, n, r in success if isinstance(r, int) and r > 2400]
print("\n" + "=" * 60)
print(f"DONE! Total time: {elapsed_total/60:.1f}min")
print(f"New downloads: {len(success)}")
print(f"Skipped (exist): {len(already)}")
print(f"Failed: {len(failed)}")
print(f"\n*** 10+ year ETFs ({len(ten_plus)}):")
for code, name, rows in sorted(ten_plus, key=lambda x: -x[2]):
    years = rows / 244
    print(f"  {code} {name:<25} {rows} rows ~{years:.1f} years")
print(f"\nFailed list:")
for code, name, reason in failed:
    print(f"  {code} {name:<25} {reason}")

# 保存结果
result = {
    "download_time": datetime.now().isoformat(),
    "total": len(ETF_LIST),
    "success": len(success),
    "skipped": len(already),
    "failed": len(failed),
    "ten_plus_years": len(ten_plus),
    "success_detail": [(c, n, r) for c, n, r in success],
    "failed_detail": [(c, n, r) for c, n, r in failed],
    "ten_plus_detail": [(c, n, r) for c, n, r in ten_plus],
}
with open(OUTPUT_DIR / "download_result.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\nResult saved: {OUTPUT_DIR / 'download_result.json'}")
print("=" * 60)
