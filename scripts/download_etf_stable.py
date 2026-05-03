"""
新浪财经ETF列表获取 + 批量下载（稳定版）
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

START_DATE = "20100101"
END_DATE = "20260407"
REQUEST_DELAY = 3.0
MAX_RETRIES = 3
BATCH_WAIT = 15
HEARTBEAT = 60

print("=" * 60)
print("ETF下载 - 新浪+已知清单版")
print(f"开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# 已知老牌ETF（成立10年以上，按类型分类）
KNOWN_ETFS = {
    "宽基_上证50": [
        ("510050", "华夏上证50ETF"),
    ],
    "宽基_沪深300": [
        ("510300", "华泰柏瑞沪深300ETF"),
        ("159919", "嘉实沪深300ETF"),
    ],
    "宽基_中证500": [
        ("510500", "南方中证500ETF"),
        ("159922", "嘉实中证500ETF"),
        ("510510", "广发中证500ETF"),
    ],
    "宽基_中证1000": [
        ("159633", "易方达中证1000ETF"),
        ("560010", "华夏中证1000ETF"),
    ],
    "宽基_创业板": [
        ("159915", "易方达创业板ETF"),
        ("159915", "易方达创业板ETF"),
    ],
    "宽基_深证100": [
        ("159901", "易方达深证100ETF"),
    ],
    "宽基_科创50": [
        ("588050", "华夏科创50ETF"),
        ("588080", "易方达科创50ETF"),
        ("588000", "华夏科创50ETF"),
    ],
    "行业_证券": [
        ("512880", "国泰中证全指证券公司ETF"),
    ],
    "行业_军工": [
        ("512660", "国泰中证军工ETF"),
    ],
    "行业_芯片": [
        ("512760", "国泰CES半导体芯片ETF"),
        ("588920", "华夏科创芯片ETF"),
    ],
    "行业_医药": [
        ("512010", "易方达沪深300医药卫生ETF"),
        ("512300", "南方中证全指医药卫生ETF"),
    ],
    "行业_消费": [
        ("159928", "汇添富中证主要消费ETF"),
    ],
    "行业_新能源": [
        ("515030", "华夏中证新能源汽车ETF"),
    ],
    "QDII_港股": [
        ("510900", "易方达恒生H股ETF"),
        ("159920", "华夏恒生ETF"),
    ],
    "QDII_纳斯达克": [
        ("513100", "国泰纳斯达克100ETF"),
        ("159941", "广发纳斯达克100ETF"),
    ],
    "QDII_标普500": [
        ("513500", "博时标普500ETF"),
    ],
    "债券": [
        ("511010", "国泰国证航天军工ETF"),
    ],
    "黄金": [
        ("518880", "国泰黄金ETF"),
    ],
}

# 展开去重
all_etf_codes = []
seen = set()
for category, etfs in KNOWN_ETFS.items():
    for code, name in etfs:
        if code not in seen:
            seen.add(code)
            all_etf_codes.append((code, name, category))

print(f"已知的10年以上ETF清单: {len(all_etf_codes)} 只")
for code, name, cat in all_etf_codes:
    print(f"  [{cat}] {code} {name}")

# 尝试从新浪补充更多ETF
sina_etfs = []
try:
    print("\n尝试从新浪获取补充ETF列表...")
    time.sleep(3)
    df_sina = ak.fund_etf_category_sina()
    if df_sina is not None and len(df_sina) > 0:
        print(f"  新浪获取成功: {len(df_sina)} 只")
        sina_codes = df_sina['symbol'].astype(str).str.zfill(6).tolist()
        for c in sina_codes:
            if c not in seen:
                seen.add(c)
                sina_etfs.append((c, "新浪ETF", "sina"))
        print(f"  补充 {len(sina_etfs)} 只新ETF")
except Exception as e:
    print(f"  新浪获取失败: {e}")

all_download = all_etf_codes + sina_etfs
print(f"\n总计待下载: {len(all_download)} 只")

# 下载函数
def download_etf(code, name, retries=MAX_RETRIES):
    save_path = OUTPUT_DIR / f"{code}.SH.csv"
    if save_path.exists():
        return "already_exists", 0
    for r in range(retries):
        try:
            time.sleep(REQUEST_DELAY + random.uniform(0, 1))
            df = ak.fund_etf_hist_em(symbol=code, period="daily",
                                     start_date=START_DATE, end_date=END_DATE, adjust="")
            if df is None or len(df) < 50:
                return "no_data", 0
            col_map = {}
            for c in df.columns:
                cs = str(c)
                if '日期' in cs: col_map[c] = 'date'
                elif '开盘' in cs: col_map[c] = 'open'
                elif '收盘' in cs: col_map[c] = 'close'
                elif '最高' in cs: col_map[c] = 'high'
                elif '最低' in cs: col_map[c] = 'low'
                elif '成交量' in cs: col_map[c] = 'volume'
                elif '成交额' in cs: col_map[c] = 'amount'
            df = df.rename(columns=col_map)
            keep = [c for c in ['date','open','high','low','close','volume','amount'] if c in df.columns]
            df = df[keep]
            df.to_csv(save_path, index=False, encoding='utf-8')
            return "success", len(df)
        except Exception as e:
            err = str(e)
            if r < retries - 1:
                time.sleep(10 * (r + 1))
            else:
                return f"fail:{err[:60]}", 0
    return "unknown", 0

# 批量下载
success = []
already = []
failed = []
t0 = time.time()
last_hb = t0

for idx, (code, name, cat) in enumerate(all_download):
    status, rows = download_etf(code, name)
    if status == "already_exists":
        already.append((code, name, rows))
    elif status == "success":
        success.append((code, name, rows))
        years = rows / 244
        flag = "***10Y+" if rows > 2400 else ""
        print(f"[{idx+1}/{len(all_download)}] {code} {name:<20} {rows:>5}行 ~{years:.1f}年 {flag}")
    else:
        failed.append((code, name, status))
        print(f"[{idx+1}/{len(all_download)}] {code} {name:<20} FAIL: {status}")

    # 心跳
    now = time.time()
    if now - last_hb >= HEARTBEAT:
        elapsed = now - t0
        rate = (idx + 1) / elapsed
        eta = (len(all_download) - idx - 1) / max(rate, 0.01)
        print(f"\n[HEARTBEAT {datetime.now().strftime('%H:%M:%S')}] "
              f"进度 {idx+1}/{len(all_download)} | "
              f"成功 {len(success)} | 已有 {len(already)} | 失败 {len(failed)} | "
              f"已{elapsed/60:.1f}min | 剩{eta/60:.1f}min")
        last_hb = now

    # 每20个等一等
    if (idx + 1) % 20 == 0 and idx + 1 < len(all_download):
        print(f"  -- 批间等待{BATCH_WAIT}s --")
        time.sleep(BATCH_WAIT)

# 汇总
total_elapsed = time.time() - t0
ten_plus = [(c, n, r) for c, n, r in success if isinstance(r, int) and r > 2400]
print("\n" + "=" * 60)
print(f"完成! 耗时 {total_elapsed/60:.1f}min")
print(f"成功下载: {len(success)}")
print(f"已有文件: {len(already)}")
print(f"下载失败: {len(failed)}")
print(f"\n**10年以上数据ETF ({len(ten_plus)}只):")
for code, name, rows in sorted(ten_plus, key=lambda x: -x[2]):
    print(f"  {code} {name:<22} {rows}行")

result = {
    "download_time": datetime.now().isoformat(),
    "total": len(all_download),
    "success": len(success),
    "already": len(already),
    "failed": len(failed),
    "ten_plus_years": len(ten_plus),
    "success_detail": [(c, n, r) for c, n, r in success],
    "failed_detail": [(c, n, r) for c, n, r in failed],
    "ten_plus_detail": [(c, n, r) for c, n, r in ten_plus],
}
with open(OUTPUT_DIR / "download_result.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\n结果: {OUTPUT_DIR / 'download_result.json'}")
print("=" * 60)
