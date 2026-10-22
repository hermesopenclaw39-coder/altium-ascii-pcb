#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""体检 Altium ASCII 原理图（SchDoc）。

输出：记录数、元件数、位号重复、封装完整性（45→44→元件链）、
引脚总数与悬空引脚、导线数。

用法：
    python sch_inspect.py 原理图.SchDoc [--json]

注意：只读，不修改文件。
"""
import argparse
import collections
import json
import re
import sys


def read_sch(path):
    raw = open(path, 'rb').read()
    if raw[:6] != b'|HEADE':
        sys.exit('不是 ASCII SchDoc（可能是二进制）。请在 AD 里 File → Save As → '
                 'Advanced Schematic ascii (*.SchDoc) 重新导出。')
    text = raw.decode('gbk', errors='replace')
    lines = [l for l in text.split('\r\n') if l.strip()]
    head, body = lines[0], lines[1:]
    recs = [dict(p.split('=', 1) for p in l.split('|') if '=' in p) for l in body]
    return head, body, recs


def kv(l):
    return dict(p.split('=', 1) for p in l.split('|') if '=' in p)


def pin_hot(k):
    """引脚的热端坐标（真正接线的那一端）。"""
    x, y = int(k['LOCATION.X']), int(k['LOCATION.Y'])
    d = int(k.get('PINCONGLOMERATE', 0)) & 3
    ln = int(k.get('PINLENGTH', 0))
    dx, dy = [(1, 0), (0, 1), (-1, 0), (0, -1)][d]
    return (x + dx * ln, y + dy * ln)


def on_segment(p, seg):
    (x1, y1), (x2, y2) = seg
    if x1 == x2 == p[0]:
        return min(y1, y2) <= p[1] <= max(y1, y2)
    if y1 == y2 == p[1]:
        return min(x1, x2) <= p[0] <= max(x1, x2)
    return False


def inspect(path):
    head, body, K = read_sch(path)
    out = {}
    out['file'] = path
    out['records'] = len(body)
    m = re.search(r'WEIGHT=(\d+)', head)
    out['weight'] = int(m.group(1)) if m else None
    out['weight_ok'] = (out['weight'] in (len(body), len(body) - 1, len(body) + 1))

    comps = {i: k for i, k in enumerate(K) if k.get('RECORD') == '1'}
    out['components'] = len(comps)

    # 位号（OWNERINDEX 可能等于元件序号或元件序号±1，自动探测）
    refs = {}
    off = 0
    best = -1
    for cand_off in (0, -1, 1):
        cand = {}
        for k in K:
            if k.get('RECORD') == '34' and k.get('NAME') == 'Designator':
                cand[int(k.get('OWNERINDEX', -1)) - cand_off] = k.get('TEXT')
        hit = sum(1 for i in comps if i in cand)
        if hit > best:
            best, refs, off = hit, cand, cand_off
    out['designators'] = len([1 for i in comps if refs.get(i)])
    dup = [n for n, c in collections.Counter(refs.get(i) for i in comps).items() if c > 1]
    out['duplicate_designators'] = dup

    # 封装链：元件 ← 44 ← 45（按本文件探测出的 OWNERINDEX 约定）
    have = set()
    for k in K:
        if k.get('RECORD') == '45' and k.get('MODELNAME'):
            o = int(k.get('OWNERINDEX', -1)) - off
            if 0 <= o < len(K) and K[o].get('RECORD') == '44':
                c = int(K[o].get('OWNERINDEX', -1)) - off
                if 0 <= c < len(K) and K[c].get('RECORD') == '1':
                    have.add(c)
    missing = [refs.get(i) for i in comps if i not in have]
    out['footprints'] = len(comps) - len(missing)
    out['missing_footprints'] = missing

    # 引脚与导线
    pins = []
    for k in K:
        if k.get('RECORD') == '2':
            pins.append((int(k.get('OWNERINDEX', -1)), k.get('DESIGNATOR'), pin_hot(k)))
    segs = [((int(k['X1']), int(k['Y1'])), (int(k['X2']), int(k['Y2'])))
            for k in K if k.get('RECORD') == '27']
    floating = []
    for owner, num_, p in pins:
        touched = any(on_segment(p, s) for s in segs)
        shared = sum(1 for _, _, q in pins if q == p)
        if not touched and shared < 2:
            floating.append({'designator': refs.get(owner - off), 'pin': num_, 'at': p})
    out['pins'] = len(pins)
    out['floating_pins'] = floating
    out['wires'] = len(segs)
    return out


def main():
    ap = argparse.ArgumentParser(description='体检 Altium ASCII 原理图')
    ap.add_argument('schdoc')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    r = inspect(a.schdoc)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print('文件 %s' % r['file'])
    print('记录 %d 条，WEIGHT=%s %s' % (r['records'], r['weight'],
                                       '(一致)' if r['weight_ok'] else '(与记录数不符!)'))
    print('元件 %d 个，位号 %d 个' % (r['components'], r['designators']))
    print('重复位号: %s' % (r['duplicate_designators'] or '无'))
    print('封装完整 %d / %d%s' % (r['footprints'], r['components'],
                                '' if not r['missing_footprints'] else
                                '，缺: %s' % r['missing_footprints'][:10]))
    print('引脚 %d 个，悬空 %d 个' % (r['pins'], len(r['floating_pins'])))
    for f in r['floating_pins'][:12]:
        print('   %-8s pin %-3s @ %s' % (f['designator'], f['pin'], f['at']))
    print('导线 %d 段' % r['wires'])


if __name__ == '__main__':
    main()
