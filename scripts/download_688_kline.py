"""
下载 588200(科创芯片ETF) 持仓的 688 科创板股票 K线数据
使用 yfinance，走本地代理 7897（环境变量方式，和已成功的SH/SZ一致）
输出目录：E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/KC/
"""
import sys, io, os, time, json, threading
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 代理必须在 import yfinance 之前设置
os.environ['HTTP_PROXY']  = 'http://127.0.0.1:7897'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7897'

import pandas as pd
import yfinance as yf
from datetime import datetime
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────
OUT_DIR = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/KC")
OUT_DIR.mkdir(parents=True, exist_ok=True)

START_DATE  = "2019-01-01"
END_DATE    = "2026-04-11"
ITEM_DELAY  = 4        # 每只间隔秒数
RETRY_WAIT  = [15, 30, 60]  # 限速重试等待

# 588200 2025Q4 持仓 688 全部代码（58只）
CODES_688 = [
    '688981','688041','688256','688008','688012','688072','688521','688347',
    '688126','688110','688498','688525','688120','688002','688249','688361',
    '688099','688313','688396','688385','688608','688213','688047','688019',
    '688037','688220','688234','688200','688052','688702','688018','688082',
    '688536','688582','688484','688141','688728','688409','688279','688709',
    '688172','688798','688153','688146','688332','688352','688432','688584',
    '688449','688605','688795','688790','688729','688809','688727','688796',
    '688807','688805',
]

# ── 心跳 ─────────────────────────────────────────────
_start_time = time.time()
_stop_hb = threading.Event()
_stats = {'done': 0, 'success': 0, 'fail': 0}

def _heartbeat():
    while not _stop_hb.wait(30):
        elapsed = time.time() - _start_time
        m, s = divmod(int(elapsed), 60)
        d = _stats['done']
        total = len(CODES_688)
        eta_s = (total - d) * (elapsed / max(d, 1))
        em, es = divmod(int(eta_s), 60)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ 进度 {d}/{total} | "
              f"成功{_stats['success']} 失败{_stats['fail']} | "
              f"已耗时{m}m{s:02d}s | 预计剩余{em}m{es:02d}s", flush=True)

hb_thread = threading.Thread(target=_heartbeat, daemon=True)
hb_thread.start()

# ── 主下载循环 ─────────────────────────────────────────
print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始下载 {len(CODES_688)} 只688科创芯片股 K线")
print(f"  代理: HTTP_PROXY=http://127.0.0.1:7897 | {START_DATE}~{END_DATE}")
print(f"  输出: {OUT_DIR}\n")

success_list, failed_list = [], []
results = {}

for idx, code in enumerate(CODES_688):
    yf_sym = f"{code}.SS"
    out_path = OUT_DIR / f"{code}.SS.csv"

    # 断点续传
    if out_path.exists() and out_path.stat().st_size > 500:
        df_check = pd.read_csv(out_path)
        if len(df_check) >= 100:
            print(f"[{idx+1}/{len(CODES_688)}] {code} ⏭️ 已存在({len(df_check)}行)，跳过")
            success_list.append(code)
            results[code] = {'rows': len(df_check), 'status': 'skip'}
            _stats['done'] += 1
            _stats['success'] += 1
            continue

    raw = None
    last_err = ''
    for attempt, wait in enumerate([0] + RETRY_WAIT):
        if wait > 0:
            print(f"  ↩️ 第{attempt+1}次重试，等待{wait}s...", flush=True)
            time.sleep(wait)
        try:
            raw = yf.download(
                tickers=yf_sym,
                start=START_DATE,
                end=END_DATE,
                auto_adjust=True,
                progress=False,
                timeout=30,
            )
            if raw is not None and len(raw) >= 20:
                break
            last_err = f'数据不足({len(raw) if raw is not None else 0}行)'
            raw = None
        except Exception as e:
            last_err = str(e)[:80]
            if 'RateLimit' not in last_err and 'Too Many' not in last_err:
                break  # 非限速错误不重试

    _stats['done'] += 1

    if raw is None or (hasattr(raw,'empty') and raw.empty):
        print(f"[{idx+1}/{len(CODES_688)}] {code} ❌ {last_err}")
        failed_list.append(code)
        results[code] = {'rows': 0, 'status': last_err}
        time.sleep(ITEM_DELAY)
        continue

    try:
        df = raw.copy()
        df.index.name = 'date'
        # 新版yfinance单股也返回MultiIndex列 (field, ticker)，需要取第一层
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() if isinstance(c, str) else str(c[0]).lower() for c in df.columns]
        keep = [c for c in ['open','high','low','close','volume'] if c in df.columns]
        df = df[keep].dropna(how='all')
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.to_csv(out_path)

        rows = len(df)
        years = rows / 244
        s_date = str(df.index[0].date())
        e_date = str(df.index[-1].date())
        success_list.append(code)
        results[code] = {'rows': rows, 'years': round(years,1), 'start': s_date, 'end': e_date, 'status': 'ok'}
        _stats['success'] += 1
        print(f"[{idx+1}/{len(CODES_688)}] {code} ✅ {rows}行({years:.1f}年) {s_date}~{e_date}", flush=True)
    except Exception as e:
        print(f"[{idx+1}/{len(CODES_688)}] {code} ❌ 保存异常: {e}")
        failed_list.append(code)
        results[code] = {'rows': 0, 'status': str(e)[:60]}
        _stats['fail'] += 1

    time.sleep(ITEM_DELAY)

# ── 收尾 ─────────────────────────────────────────────
_stop_hb.set()
elapsed = time.time() - _start_time
m, s = divmod(int(elapsed), 60)

print(f"\n{'='*60}")
print(f"[{datetime.now().strftime('%H:%M:%S')}] 下载完成！耗时 {m}m{s:02d}s")
print(f"成功: {len(success_list)}/{len(CODES_688)} 只")
if failed_list:
    print(f"失败({len(failed_list)}只): {failed_list}")

ok = [v for v in results.values() if v.get('status')=='ok']
if ok:
    yrs = [v['years'] for v in ok]
    print(f"平均年限: {sum(yrs)/len(yrs):.1f}年 | 3年+: {sum(1 for y in yrs if y>=3)} | 5年+: {sum(1 for y in yrs if y>=5)}")

json.dump({'success': success_list, 'failed': failed_list, 'details': results},
          open(OUT_DIR / 'result_688.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f"结果已保存: {OUT_DIR / 'result_688.json'}")
