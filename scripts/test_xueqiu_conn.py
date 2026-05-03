"""测试雪球API连接方式"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import requests

PROXIES_7897 = {'http': 'http://127.0.0.1:7897', 'https': 'http://127.0.0.1:7897'}
PROXIES_7890 = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

for name, kwargs in [
    ('直连', {}),
    ('代理7897', {'proxies': PROXIES_7897}),
    ('代理7890', {'proxies': PROXIES_7890}),
]:
    try:
        r = requests.get('https://xueqiu.com/', headers=headers, timeout=6,
                         verify=False, **kwargs)
        cookies = dict(r.cookies)
        print(f'{name}: {r.status_code}, cookies={list(cookies.keys())}')
        # 如果有 xq_a_token 说明可以直接用
        if 'xq_a_token' in cookies:
            print(f'  >>> xq_a_token 找到！')
        if r.status_code == 200:
            print(f'  >>> {name} 可用！')
            break
    except Exception as e:
        print(f'{name}: 失败 - {type(e).__name__}: {str(e)[:80]}')
