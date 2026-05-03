"""
扫描有10年以上历史数据的股票
"""
import pandas as pd
from pathlib import Path

data_dir = Path('E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/20100101_20260407')
files = sorted(data_dir.glob('*.csv'))

print(f"开始扫描，共 {len(files)} 个文件...")

results = []
for i, fp in enumerate(files):
    if i % 200 == 0:
        print(f"  已处理 {i}/{len(files)}...")
    try:
        df = pd.read_csv(fp, usecols=['date'])
        start = pd.to_datetime(df['date'].min())
        end = pd.to_datetime(df['date'].max())
        days = len(df)
        results.append({'symbol': fp.stem, 'start': start, 'end': end, 'days': days})
    except Exception as e:
        pass

df_all = pd.DataFrame(results)
df_all['years'] = (df_all['end'] - df_all['start']).dt.days / 365.25

# 10年以上 = 起始在2016-01-01以前（截至2026年，至少10年）
df_10y = df_all[df_all['start'] <= '2016-01-01'].sort_values('start')

print(f"\n总股票数: {len(df_all)}")
print(f"10年以上(2016前起始)股票数: {len(df_10y)}")
print()

# 按前缀分类
for prefix in ['600', '601', '603']:
    sub = df_10y[df_10y['symbol'].str.startswith(prefix)]
    print(f"  {prefix}开头: {len(sub)} 只")

print()
print("最早上市的前30只:")
print(f"{'代码':<22} {'起始日期':<14} {'结束日期':<14} {'交易日数':>8} {'年数':>6}")
print("-"*68)
for _, row in df_10y.head(30).iterrows():
    print(f"  {row['symbol']:<20} {row['start'].strftime('%Y-%m-%d'):<14} {row['end'].strftime('%Y-%m-%d'):<14} {row['days']:>8} {row['years']:>5.1f}年")

# 保存完整列表
out_file = 'e:/dzhwork/quant/quant_lab/data/stocks_10y_plus.csv'
df_10y.to_csv(out_file, index=False, encoding='utf-8-sig')
print(f"\n完整列表已保存到: {out_file}")

# 按前缀分别输出列表（用于选股）
print("\n===== 603系列（沪市科技/成长股）完整列表 =====")
df_603 = df_10y[df_10y['symbol'].str.startswith('603')]
print(f"共 {len(df_603)} 只，列表：")
for sym in df_603['symbol'].tolist():
    print(f"  {sym}")
