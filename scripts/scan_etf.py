import pandas as pd
from pathlib import Path

data_dir = Path('E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/20100101_20260407')
files = sorted(data_dir.glob('*.csv'))

# ETF基金代码范围（中国A股）
# 上交所ETF: 51xxxx, 56xxxx, 58xxxx
# 深交所ETF: 15xxxx, 16xxxx
# 上交所LOF: 50xxxx
# 场外基金: 000/001/002/003/004/005/006开头

etf_prefixes = ['51', '56', '58', '15', '16', '50']
etf_files = []
all_files = []

for fp in files:
    prefix = fp.stem[:2]
    all_files.append((fp.stem, prefix))
    if prefix in etf_prefixes:
        etf_files.append(fp.stem)

print(f"总文件数: {len(files)}")

# 按前缀分组
from collections import Counter
prefixes = [f[1] for f in all_files]
counts = Counter(prefixes)
print("\n所有前缀分布:")
for p, c in sorted(counts.items()):
    print(f"  {p}: {c}只")

print(f"\n疑似ETF/基金文件 (51/56/58/15/16/50开头): {len(etf_files)}只")
if etf_files:
    for f in sorted(etf_files):
        print(f"  {f}")
else:
    print("  无ETF文件！")

# 再检查其他可能的基金前缀
other_fund_prefixes = ['00', '01', '04', '16']
fund_files = [f for f, p in all_files if p in other_fund_prefixes]
print(f"\n其他疑似基金文件: {len(fund_files)}只")
if fund_files:
    for f in sorted(fund_files)[:30]:
        print(f"  {f}")
