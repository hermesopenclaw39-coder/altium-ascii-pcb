#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""体检 Altium ASCII PCB（PcbDoc）。

检查项：
  * 元件 / 焊盘 / 网络数量
  * 元件是否超出板框、元件外框是否互相重叠
  * 走线是否走出板框
  * 每个网络是否完全连通（按走线端点 + 焊盘做并查集）
  * 同层不同网络的走线是否交叉（潜在短路）

用法：
    python pcb_inspect.py 板子.PcbDoc [--json]

只读，不修改文件。板框取自 KeepOut 层的走线包围盒。
"""
import argparse
import collections
import json
import sys

TOL = 13.0        # 判定"端点落在焊盘上"的容差（mil）
MIL = 'mil'


def num(v):
    return float(v[:-3]) if v.endswith(MIL) else float(v)


def read_pcb(path):
    raw = open(path, 'rb').read()
    if raw[:2] != b'|R':
        sys.exit('不是 ASCII PcbDoc（可能是二进制）。请在 AD 里 File → Save As → '
                 'PCB ASCII File (*.PcbDoc) 重新导出。')
    # PcbDoc 的路径字段含 GBK 字节，必须用 latin-1
    text = raw.decode('latin-1')
    return [l for l in text.split('\r\n') if l.strip()]


def kv(l):
    return dict(p.split('=', 1) for p in l.split('|') if '=' in p)


def bbox_of(K, comps):
    bb = collections.defaultdict(lambda: [1e9, 1e9, -1e9, -1e9])
    for k in K:
        if 'COMPONENT' not in k or k.get('RECORD') == 'Text':
            continue
        cid = int(k['COMPONENT'])
        if cid not in comps:
            continue
        r = k.get('RECORD')
        if r == 'Pad':
            pts = [(num(k['X']), num(k['Y']))]
        elif r in ('Track', 'Fill'):
            pts = [(num(k['X1']), num(k['Y1'])), (num(k['X2']), num(k['Y2']))]
        elif r == 'Arc':
            cx, cy, rad = num(k['LOCATION.X']), num(k['LOCATION.Y']), num(k['RADIUS'])
            pts = [(cx - rad, cy - rad), (cx + rad, cy + rad)]
        else:
            continue
        for x, y in pts:
            b = bb[cid]
            b[0], b[1] = min(b[0], x), min(b[1], y)
            b[2], b[3] = max(b[2], x), max(b[3], y)
    return bb


def find(p, par):
    r = p
    while par[r] != r:
        r = par[r]
    while par[p] != r:
        par[p], p = r, par[p]
    return r


def inspect(path):
    ls = read_pcb(path)
    K = [kv(l) for l in ls if l.startswith('|RECORD=')]
    comps = {int(k['ID']): k for k in K if k.get('RECORD') == 'Component'}
    pads = [k for k in K if k.get('RECORD') == 'Pad']
    nets = {int(k['ID']): k.get('NAME') for k in K if k.get('RECORD') == 'Net'}
    tr = [k for k in K if k.get('RECORD') == 'Track' and 'NET' in k]

    # 板框：KeepOut 层走线的包围盒
    ko = [k for k in K if k.get('RECORD') == 'Track' and k.get('LAYER') == 'KEEPOUT']
    if ko:
        xs = [num(k[a]) for k in ko for a in ('X1', 'X2')]
        ys = [num(k[a]) for k in ko for a in ('Y1', 'Y2')]
        X0, X1, Y0, Y1 = min(xs), max(xs), min(ys), max(ys)
    else:
        X0 = Y0 = -1e18
        X1 = Y1 = 1e18

    out = dict(file=path, records=len(ls), components=len(comps),
               pads=len(pads), nets=len(nets), routed_segments=len(tr),
               board=[round(X0, 2), round(Y0, 2), round(X1, 2), round(Y1, 2)])

    bb = bbox_of(K, comps)
    out['out_of_board'] = [comps[c].get('SOURCEDESIGNATOR') for c in comps
                           if c in bb and (bb[c][0] < X0 - 1 or bb[c][2] > X1 + 1
                                           or bb[c][1] < Y0 - 1 or bb[c][3] > Y1 + 1)]
    items = [(comps[c].get('SOURCEDESIGNATOR'), bb[c]) for c in comps if c in bb]
    ov = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i][1], items[j][1]
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                ov.append((items[i][0], items[j][0]))
    out['overlaps'] = ov
    out['tracks_out_of_board'] = sum(
        1 for k in tr
        if min(num(k['X1']), num(k['X2'])) < X0 - 5 or max(num(k['X1']), num(k['X2'])) > X1 + 5
        or min(num(k['Y1']), num(k['Y2'])) < Y0 - 5 or max(num(k['Y1']), num(k['Y2'])) > Y1 + 5)

    # 连通性
    G = collections.defaultdict(list)
    for k in pads:
        G[int(k.get('NET', -1))].append((round(num(k['X']), 2), round(num(k['Y']), 2)))
    bad, ok = [], 0
    for nid, ps in G.items():
        if nid < 0 or len(ps) < 2:
            continue
        segs = [((round(num(k['X1']), 2), round(num(k['Y1']), 2)),
                 (round(num(k['X2']), 2), round(num(k['Y2']), 2)))
                for k in tr if int(k['NET']) == nid]
        pts = set(ps)
        for a, b in segs:
            pts.add(a)
            pts.add(b)
        par = {p: p for p in pts}
        for a, b in segs:
            ra, rb = find(a, par), find(b, par)
            if ra != rb:
                par[ra] = rb
            for p in ps:
                if abs(p[0] - a[0]) <= TOL and abs(p[1] - a[1]) <= TOL:
                    r1, r2 = find(a, par), find(p, par)
                    if r1 != r2:
                        par[r1] = r2
                if abs(p[0] - b[0]) <= TOL and abs(p[1] - b[1]) <= TOL:
                    r1, r2 = find(b, par), find(p, par)
                    if r1 != r2:
                        par[r1] = r2
        roots = {find(p, par) for p in ps}
        if len(roots) > 1:
            bad.append({'net': nets.get(nid, nid), 'pads': len(ps), 'groups': len(roots)})
        else:
            ok += 1
    out['fully_connected_nets'] = ok
    out['incomplete_nets'] = sorted(bad, key=lambda x: -x['pads'])

    # 同层短路
    def inter(a, b, c, d):
        def ori(p, q, r):
            v = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
            return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)
        o1, o2, o3, o4 = ori(a, b, c), ori(a, b, d), ori(c, d, a), ori(c, d, b)
        return o1 != o2 and o3 != o4

    by = collections.defaultdict(list)
    for k in tr:
        by[(k.get('LAYER'), int(k['NET']))].append(k)
    keys = list(by)
    shorts = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            k1, k2 = keys[i], keys[j]
            if k1[0] != k2[0] or k1[1] == k2[1]:
                continue
            hit = False
            for A in by[k1]:
                a1 = (num(A['X1']), num(A['Y1']))
                b1 = (num(A['X2']), num(A['Y2']))
                for B in by[k2]:
                    a2 = (num(B['X1']), num(B['Y1']))
                    b2 = (num(B['X2']), num(B['Y2']))
                    if inter(a1, b1, a2, b2):
                        shorts.append((nets.get(k1[1]), nets.get(k2[1]), k1[0]))
                        hit = True
                        break
                if hit:
                    break
    out['same_layer_crossings'] = shorts
    return out


def main():
    ap = argparse.ArgumentParser(description='体检 Altium ASCII PCB')
    ap.add_argument('pcbdoc')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    r = inspect(a.pcbdoc)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print('文件 %s' % r['file'])
    print('记录 %d 条；元件 %d，焊盘 %d，网络 %d，走线 %d 段' %
          (r['records'], r['components'], r['pads'], r['nets'], r['routed_segments']))
    print('板框 X %.1f~%.1f  Y %.1f~%.1f mil' % (r['board'][0], r['board'][2],
                                                r['board'][1], r['board'][3]))
    print('元件出板: %s' % (r['out_of_board'] or '无'))
    print('元件外框重叠: %d 对 %s' % (len(r['overlaps']), r['overlaps'][:6]))
    print('走线出板: %d 段' % r['tracks_out_of_board'])
    print('完全连通网络: %d 个；不完整: %d 个' %
          (r['fully_connected_nets'], len(r['incomplete_nets'])))
    for n in r['incomplete_nets'][:12]:
        print('   %-16s 焊盘%2d → %d 块' % (n['net'], n['pads'], n['groups']))
    print('同层不同网络交叉（潜在短路）: %d 处 %s' %
          (len(r['same_layer_crossings']), r['same_layer_crossings'][:5]))


if __name__ == '__main__':
    main()
