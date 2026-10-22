#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 Altium ASCII 原理图批量补 PCB 封装（RECORD=45）。

核心规则（写错必崩 AD）：
  1. 45/46/48 必须**紧跟在元件的 RECORD=44 之后**，不能追加到文件末尾；
  2. 插入后**全表 OWNERINDEX 重映射**（OWNERINDEX = 父记录位置 + off，
     位置从表头之后第一条记为 0；off 按文件自动探测，AD 导出的文件为 0）；
  3. 不写 INDEXINSHEET（AD 自己存的文件里没有这个字段）。

用法：
    python sch_add_footprints.py 原理图.SchDoc --map footprint_map.json
    python sch_add_footprints.py 原理图.SchDoc --map m.json --dry-run

footprint_map.json 形如：
    {"Resistor": "AXIAL-0.4", "Capacitor": "RAD-0.1", "741_DIP8": "DIP-8"}

默认会先备份为 <文件名>.bak_fp。
"""
import argparse
import collections
import json
import os
import re
import shutil
import sys

DESC = {
    'AXIAL-0.4': 'Axial; 0.4 inch lead spacing',
    'RAD-0.1': 'Radial; 0.1 inch',
    'CAPPR5-5x5': 'Radial polarized; 5x5 mm',
    'DO-35': 'DO-35; axial diode',
    'TO-92': 'TO-92; 3 leads',
    'DIP-8': 'DIP; 8 Leads; Row Spacing 7.62 mm; Pitch 2.54 mm',
    'PIN1': 'Single pin',
    'VR3': 'Variable resistor; 3 pins',
    'HDR1X2': 'Header; 2 pins',
    'HDR1X3': 'Header; 3 pins',
}


def kv(l):
    return dict(p.split('=', 1) for p in l.split('|') if '=' in p)


def main():
    ap = argparse.ArgumentParser(description='批量补原理图封装')
    ap.add_argument('schdoc')
    ap.add_argument('--map', required=True, help='LIBREFERENCE → 封装名 的 JSON')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    raw = open(a.schdoc, 'rb').read()
    if raw[:6] != b'|HEADE':
        sys.exit('不是 ASCII SchDoc（可能已被 AD 存成二进制），请重新导出 ASCII。')
    text = raw.decode('gbk')
    lines = [l for l in text.split('\r\n') if l.strip()]
    head, body = lines[0], lines[1:]
    K = [kv(l) for l in body]

    fpmap = json.load(open(a.map, encoding='utf-8'))

    # 探测 OWNERINDEX 偏移：子记录序号 - off = 所属元件的序号
    off = 0
    best = -1
    for cand in (0, -1, 1):
        hit = 0
        for k in K:
            if k.get('RECORD') == '34' and k.get('NAME') == 'Designator':
                o = int(k.get('OWNERINDEX', -1)) - cand
                if 0 <= o < len(K) and K[o].get('RECORD') == '1':
                    hit += 1
        if hit > best:
            best, off = hit, cand

    comps = [i for i, k in enumerate(K) if k.get('RECORD') == '1']
    children = collections.defaultdict(list)
    for i, k in enumerate(K):
        if k.get('RECORD') == '1' or 'OWNERINDEX' not in k:
            continue
        o = int(k['OWNERINDEX']) - off
        if 0 <= o < len(K) and K[o].get('RECORD') == '1':
            children[o].append(i)

    # 已有封装的元件（45 → 44 → 元件）。45→44 与 44→元件 用同一个 off，
    # 否则在 off≠0 的文件上认不出已有封装，重复运行会把封装再插一遍。
    have = set()
    for k in K:
        if k.get('RECORD') == '45' and k.get('MODELNAME'):
            o = int(k.get('OWNERINDEX', -1)) - off
            if 0 <= o < len(K) and K[o].get('RECORD') == '44':
                have.add(int(K[o].get('OWNERINDEX', -1)) - off)

    # 插入点 → (封装, 描述)。有 44 就插在 44 之后；没有 44 就插在该元件子记录块的末尾
    need = {}
    unmapped = set()
    for c in comps:
        if c in have:
            continue
        lib = K[c].get('LIBREFERENCE', '')
        if lib not in fpmap:
            unmapped.add(lib)
            continue
        r44 = [i for i in children[c] if K[i].get('RECORD') == '44']
        anchor = r44[0] if r44 else (max(children[c]) if children[c] else c)
        fp = fpmap[lib]
        need[anchor] = (fp, DESC.get(fp, fp), bool(r44), c)

    print('元件 %d 个，已有封装 %d 个，本次补 %d 个' %
          (len(comps), len(have), len(need)))
    if unmapped:
        print('未在映射表里的库元件（已跳过）: %s' % sorted(unmapped))
    if not need:
        print('无需修改。')
        return
    if a.dry_run:
        print('dry-run，未写文件。')
        return

    # 构建新记录序列：遇到 44 就紧随其后插入 45/46/48
    new = []
    omap = {}
    for old in range(len(body)):
        omap[old] = len(new)
        new.append(('keep', old))
        if old in need:
            fp, desc, has44, cidx = need[old]
            if has44:
                p44 = len(new) - 1                 # 锚点本身就是 44
            else:
                p44 = len(new)                     # 先补一条 44
                new.append(('new', '|RECORD=44|OWNERINDEX=%d' % (omap[cidx] + off)))
            p45 = len(new)
            new.append(('new', '|RECORD=45|OWNERINDEX=%d|DESCRIPTION=%s|MODELNAME=%s'
                               '|MODELTYPE=PCBLIB|DATAFILECOUNT=1|MODELDATAFILEENTITY0=%s'
                               '|MODELDATAFILEKIND0=PCBLib|ISCURRENT=T'
                        % (p44 + off, desc, fp, fp)))
            new.append(('new', '|RECORD=46|OWNERINDEX=%d' % (p45 + off)))
            new.append(('new', '|RECORD=48|OWNERINDEX=%d' % (p45 + off)))

    out = []
    for typ, val in new:
        if typ == 'new':
            out.append(val)
            continue
        l = body[val]
        m = re.search(r'\|OWNERINDEX=(-?\d+)', l)
        if m:
            o = int(m.group(1))
            # 文件自身的约定：OWNERINDEX = 父记录序号 + off
            tgt = o - off
            if tgt in omap:
                l = l[:m.start()] + '|OWNERINDEX=%d' % (omap[tgt] + off) + l[m.end():]
            elif o in omap:
                l = l[:m.start()] + '|OWNERINDEX=%d' % omap[o] + l[m.end():]
        out.append(l)

    # WEIGHT：AD 导出文件的规律是 记录数-1
    weight = len(out) - 1
    head = re.sub(r'WEIGHT=\d+', 'WEIGHT=%d' % weight, head)

    bak = a.schdoc + '.bak_fp'
    if not os.path.exists(bak):
        shutil.copyfile(a.schdoc, bak)
        print('已备份 → %s' % bak)
    open(a.schdoc, 'wb').write(('\r\n'.join([head] + out) + '\r\n').encode('gbk'))
    print('完成：%d 条记录，WEIGHT=%d。请用 sch_inspect.py 复检。' % (len(out), weight))


if __name__ == '__main__':
    main()
