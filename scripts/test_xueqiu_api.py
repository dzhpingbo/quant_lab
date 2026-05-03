"""测试雪球API - 完整token获取流程"""
import sys, warnings, os, re
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(encoding='utf-8')
import requests, json, time

os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

session = requests.Session()
session.verify = False
session.trust_env = False

headers_browser = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  'Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Cache-Control': 'max-age=0',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
}

# Step1: 主页
print("[Step1] 主页...")
r0 = session.get('https://xueqiu.com/', headers=headers_browser, timeout=12)
print(f"  状态: {r0.status_code}, cookies: {dict(session.cookies)}")

# 尝试从JS中提取 xq_a_token
for script_url in re.findall(r'src="(/assets/[^"]+\.js)"', r0.text):
    pass  # 不走这条路，太复杂

# Step2: 尝试雪球的 token API 接口
print("\n[Step2] token接口...")
r_token = session.get(
    'https://xueqiu.com/service/v5/stock/realtime/quotec',
    params={'symbol': 'SH000001'},
    headers={**headers_browser,
             'Accept': 'application/json',
             'Referer': 'https://xueqiu.com/',
             'Sec-Fetch-Site': 'same-origin'},
    timeout=10
)
print(f"  状态: {r_token.status_code}")
print(f"  返回: {r_token.text[:300]}")
print(f"  cookies after: {dict(session.cookies)}")

# Step3: 尝试 xueqiu.com/service 接口
print("\n[Step3] service接口...")
r_svc = session.get(
    'https://xueqiu.com/hq/d/v3/feed.json',
    params={'pid': '1000', 'type': 'S_SH_600000', 'max_id': '-1', 'count': '1'},
    headers={**headers_browser, 'Accept': 'application/json'},
    timeout=10
)
print(f"  状态: {r_svc.status_code}, 返回: {r_svc.text[:200]}")

# Step4: 尝试 akshare 的雪球接口
print("\n[Step4] akshare 雪球数据...")
try:
    import akshare as ak
    # 股票实时行情
    df_rt = ak.stock_zh_a_spot_em()
    print(f"  东财实时: {df_rt.shape}, 列: {df_rt.columns.tolist()[:8]}")
    print(f"  600000行: {df_rt[df_rt['代码']=='600000'][['名称','最新价','市盈率-动态','市净率']].to_string()}")
except Exception as e:
    print(f"  错误: {e}")
