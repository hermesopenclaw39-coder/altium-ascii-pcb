#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按分区把 PCB 器件摆进板框，并把位号移到元件正上方。

关键点：必须按**元件真实外框**（Pad/Track/Arc/Fill，不含位号文字）计算占位，
否则高件（如 34mm 电位器）会顶出板框。高件单独占竖条，其余自适应列数。

用法：
    python pcb_place.py 板子.PcbDoc --blocks blocks.csv [--cols 3] [--rows 3]
                         [--out 新文件.PcbDoc] [--no-designator]

blocks.csv 两列：Designator,Block   （Block 取 A..I，按阅读顺序上→下、左→右）

元件图元用 COMPONENT=<ID> 归属，移动时同步平移 Pad/Track/Arc/Text/Fill。
"""
import argparse
import collections
import csv
import os
import re
import shutil
import sys

TALL = 600.0        # 外框高于此值视为"高件"（mil）
MARGIN = 170.0


def num(v):
    return float(v[:-3]) if v.endswith('mil') else float(v)


def kv(l):
    return dict(p.split('=', 1) for p in l.split('|') if '=' in p)


def setfield(l, key, val):
    if ('|%s=' % key) in l:
        return re.sub(r'\|%s=[^|]*' % key, '|%s=%s' % (key, val), l, count=1)
    return l + '|%s=%s' % (key, val)


def shift(l, dx, dy):
    out = []
    for part in l.split('|'):
        if '=' in part:
            a, b = part.split('=', 1)
            if a in ('X', 'X1', 'X2', 'LOCATION.X') and b.endswith('mil'):
                b = '%.4fmil' % (float(b[:-3]) + dx)
            elif a in ('Y', 'Y1', 'Y2', 'LOCATION.Y') and b.endswith('mil'):
                b = '%.4fmil' % (float(b[:-3]) + dy)
            part = a + '=' + b
        out.append(part)
    return '|'.join(out)


def main():
    ap = argparse.ArgumentParser(description='按分区摆放 PCB 器件')
    ap.add_argument('pcbdoc')
    ap.add_argument('--blocks', required=True, help='Designator,Block 的 CSV')
    ap.add_argument('--cols', type=int, default=3)
    ap.add_argument('--rows', type=int, default=3)
    ap.add_argument('--out', default=None)
    ap.add_argument('--no-designator', action='store_true', help='不移动位号文字')
    a = ap.parse_args()

    raw = open(a.pcbdoc, 'rb').read()
    if raw[:2] != b'|R':
        sys.exit('不是 ASCII PcbDoc（可能已被 AD 存成二进制），请重新导出 ASCII。')
    ls = [l for l in raw.decode('latin-1').split('\r\n') if l.strip()]
    K = [kv(l) for l in ls if l.startswith('|RECORD=')]
    comps = {int(k['ID']): k for k in K if k.get('RECORD') == 'Component'}

    # 板框
    ko = [k for k in K if k.get('RECORD') == 'Track' and k.get('LAYER') == 'KEEPOUT']
    if not ko:
        sys.exit('找不到 KeepOut 层的板框走线，无法确定板框。')
    X0 = min(num(k[x]) for k in ko for x in ('X1', 'X2'))
    X1 = max(num(k[x]) for k in ko for x in ('X1', 'X2'))
    Y0 = min(num(k[y]) for k in ko for y in ('Y1', 'Y2'))
    Y1 = max(num(k[y]) for k in ko for y in ('Y1', 'Y2'))

    # 每个元件的外框（不含 Text）
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

    info = {}
    for cid, k in comps.items():
        ox, oy = num(k['X']), num(k['Y'])
        b = bb[cid]
        info[cid] = dict(des=k.get('SOURCEDESIGNATOR', ''), ox=ox, oy=oy,
                         l=b[0] - ox, r=b[2] - ox, b=b[1] - oy, t=b[3] - oy)

    blk = {}
    with open(a.blocks, encoding='gbk') as f:
        for row in csv.DictReader(f):
            blk[row['Designator']] = row['Block']

    groups = collections.defaultdict(list)
    for cid, i in info.items():
        groups[blk.get(i['des'], 'A')].append(cid)

    BW = (X1 - X0) / a.cols
    BH = (Y1 - Y0) / a.rows
    tgt = {}
    for b, cids in groups.items():
        idx = 'ABCDEFGHI'.index(b) if b in 'ABCDEFGHI' else 0
        bx = X0 + (idx % a.cols) * BW
        by = Y0 + (idx // a.cols) * BH
        tall = sorted([c for c in cids if info[c]['t'] - info[c]['b'] > TALL],
                      key=lambda c: info[c]['des'])
        norm = sorted([c for c in cids if c not in tall], key=lambda c: info[c]['des'])
        sx = bx + MARGIN
        for c in tall:                                  # 高件竖排在块左侧，按外框居中
            i = info[c]
            w = i['r'] - i['l']
            tgt[c] = (sx - w / 2 - i['l'], by + BH / 2 - (i['b'] + i['t']) / 2)
            sx += w + 110
        nx0, nx1 = sx + 40, bx + BW - MARGIN + 20
        mw = max((info[c]['r'] - info[c]['l'] for c in norm), default=200) + 70
        mh = max((info[c]['t'] - info[c]['b'] for c in norm), default=200) + 60
        cols = max(1, int((nx1 - nx0) / mw))
        rows = max(1, (len(norm) + cols - 1) // cols)
        while rows * mh > (BH - 300) and cols < max(1, len(norm)):
            cols += 1
            rows = (len(norm) + cols - 1) // cols
        cw = (nx1 - nx0) / cols
        ch = (BH - 300) / rows
        for k, c in enumerate(norm):
            tgt[c] = (nx0 + cw * (k % cols + 0.5), by + 150 + ch * (k // cols + 0.5))

    bad = [info[c]['des'] for c, (x, y) in tgt.items()
           if x + info[c]['l'] < X0 or x + info[c]['r'] > X1
           or y + info[c]['b'] < Y0 or y + info[c]['t'] > Y1]
    print('摆放 %d 个元件，出板 %d 个 %s' % (len(tgt), len(bad), bad[:6]))

    delta = {c: (tgt[c][0] - info[c]['ox'], tgt[c][1] - info[c]['oy']) for c in tgt}
    out = []
    for l in ls:
        k = kv(l)
        if k.get('RECORD') == 'Component':
            cid = int(k['ID'])
            if cid in delta:
                l = setfield(shift(l, *delta[cid]), 'COMMENTON', 'FALSE')
            out.append(l)
        elif 'COMPONENT' in k and k.get('RECORD') == 'Text':
            cid = int(k['COMPONENT'])
            if (not a.no_designator) and cid in tgt and k.get('TEXT') == info[cid]['des']:
                i = info[cid]
                x, y = tgt[cid]
                l = setfield(l, 'X', '%.3fmil' % (x + i['l']))
                l = setfield(l, 'Y', '%.3fmil' % (y + i['t'] + 70))
                l = setfield(l, 'HEIGHT', '40mil')
            out.append(l)
        elif 'COMPONENT' in k and k.get('RECORD') in ('Pad', 'Track', 'Arc', 'Fill'):
            cid = int(k['COMPONENT'])
            out.append(shift(l, *delta[cid]) if cid in delta else l)
        else:
            out.append(l)

    dst = a.out or a.pcbdoc
    if dst == a.pcbdoc:
        bak = a.pcbdoc + '.bak_place'
        if not os.path.exists(bak):
            shutil.copyfile(a.pcbdoc, bak)
            print('已备份 → %s' % bak)
    open(dst, 'wb').write(('\r\n'.join(out) + '\r\n').encode('latin-1'))
    print('已写入 %s（%d 条）。请用 pcb_inspect.py 复检。' % (dst, len(out)))


if __name__ == '__main__':
    main()
