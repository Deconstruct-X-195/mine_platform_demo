# -*- coding: utf-8 -*-
"""
并发冒烟压测（上线前检查 · 性能层）：
30 线程 × 20 秒，只读接口混合负载（登录成功 + 列表/详情/字典轮询 + 健康检查）。
判据：err == 0 且 ok > 500（waitress threads=8 下即可达标）。
用法：python mine_audit_smoke.py   （需服务已在 127.0.0.1:8000 运行）
"""
import json
import statistics
import threading
import time
import urllib.error
import urllib.request

API = 'http://127.0.0.1:8000/api/v1'
HEALTH = 'http://127.0.0.1:8000/health'
THREADS = 30
DURATION = 20.0
STEEL = {'username': '13800000001', 'password': 'demo123456'}

_lock = threading.Lock()
stats = {}          # name -> [ok, err, latencies]
stop_at = 0.0


def stat(name, ok, lat):
    with _lock:
        s = stats.setdefault(name, [0, 0, []])
        s[0 if ok else 1] += 1
        s[2].append(lat)


def req(path, tok=None, base=API, parse=True):
    """单次请求，返回 (ok, latency)。5xx/4xx/超时均计 err；parse=True 时非 JSON 也计 err。"""
    t0 = time.perf_counter()
    try:
        r = urllib.request.Request(base + path, method='GET')
        if tok:
            r.add_header('Authorization', 'Bearer ' + tok)
        with urllib.request.urlopen(r, timeout=10) as resp:
            body = resp.read()
            code = resp.getcode()
        ok = code == 200
        if ok and parse:
            json.loads(body.decode('utf-8'))  # 解析失败也计 err
    except urllib.error.HTTPError as e:
        e.read()
        ok = False
    except Exception:
        ok = False
    return ok, (time.perf_counter() - t0) * 1000


def worker(idx):
    # 登录一次（成功登录不计入循环统计）
    t0 = time.perf_counter()
    try:
        r = urllib.request.Request(API + '/auth/login', method='POST')
        r.add_header('Content-Type', 'application/json')
        r.data = json.dumps(STEEL).encode()
        with urllib.request.urlopen(r, timeout=10) as resp:
            tok = json.loads(resp.read().decode())['data']['token']
        stat('login', True, (time.perf_counter() - t0) * 1000)
    except Exception as e:
        print('线程 %d 登录失败：%s' % (idx, e))
        stat('login', False, (time.perf_counter() - t0) * 1000)
        return

    seq = ['/orders', '/inquiries', '/base/varieties', '/base-prices/ports', '/orders?page=2']
    i = 0
    while time.perf_counter() < stop_at:
        name = seq[i % len(seq)]
        i += 1
        ok, lat = req(name, tok)
        stat(name, ok, lat)
        if i % 5 == 0:
            ok, lat = req('', base=HEALTH, parse=False)  # /health 返回纯文本
            stat('health', ok, lat)


def main():
    global stop_at
    print('并发冒烟压测：%d 线程 × %.0fs，混合只读负载...' % (THREADS, DURATION))
    stop_at = time.perf_counter() + DURATION
    ts = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(THREADS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(DURATION + 30)

    total_ok = total_err = 0
    lats_all = []
    print('\n%-18s %8s %8s %10s %10s %10s' % ('接口', 'OK', 'ERR', 'avg(ms)', 'p95(ms)', 'max(ms)'))
    for name, (ok, err, lats) in sorted(stats.items()):
        total_ok += ok
        total_err += err
        lats.sort()
        p95 = lats[int(len(lats) * 0.95) - 1] if lats else 0
        lats_all.extend(lats)
        print('%-18s %8d %8d %10.1f %10.1f %10.1f'
              % (name, ok, err, statistics.mean(lats), p95, max(lats)))
    lats_all.sort()
    p95 = lats_all[int(len(lats_all) * 0.95) - 1] if lats_all else 0
    print('-' * 70)
    print('合计 OK=%d  ERR=%d  QPS=%.1f  全局p95=%.1fms' % (total_ok, total_err, total_ok / DURATION, p95))

    passed = total_err == 0 and total_ok > 500
    print('判定：%s（判据 err==0 且 ok>500）' % ('PASS' if passed else 'FAIL'))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
