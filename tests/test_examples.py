#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对 examples/ 跑一遍四个脚本，只依赖标准库。

用法：python tests/test_examples.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, 'scripts')
EXAMPLES = os.path.join(ROOT, 'examples')
FPMAP = os.path.join(EXAMPLES, 'footprint_map.example.json')


def run(script, *args):
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + list(args),
                       capture_output=True)
    out = p.stdout.decode('utf-8', 'replace') + p.stderr.decode('utf-8', 'replace')
    if p.returncode != 0:
        raise AssertionError('%s 失败 (rc=%d):\n%s' % (script, p.returncode, out))
    return out


def count_45(path):
    return open(path, 'rb').read().count(b'|RECORD=45|')


def shift_owner_index(src, dst, delta):
    """把文件改写成 off=delta 的约定（模拟非 AD 生成的文件）。"""
    import re
    lines = open(src, 'rb').read().decode('gbk').split('\r\n')
    fixed = [re.sub(r'\|OWNERINDEX=(-?\d+)',
                    lambda m: '|OWNERINDEX=%d' % (int(m.group(1)) + delta), l)
             for l in lines]
    open(dst, 'wb').write('\r\n'.join(fixed).encode('gbk'))


def check_footprints(sch, label):
    out = run('sch_add_footprints.py', sch, '--map', FPMAP)
    assert '本次补 2 个' in out, out
    out = run('sch_inspect.py', sch)
    assert '封装完整 2 / 2' in out, out
    n = count_45(sch)
    out = run('sch_add_footprints.py', sch, '--map', FPMAP)   # 重复运行应无改动
    assert '本次补 0 个' in out and count_45(sch) == n, out
    print('ok  %s：批量加封装 + 复检 + 重复运行不重复插入' % label)


def main():
    tmp = tempfile.mkdtemp(prefix='altium-ascii-test-')
    try:
        sch = os.path.join(tmp, 'minimal.SchDoc')
        shutil.copy(os.path.join(EXAMPLES, 'minimal.SchDoc'), sch)
        out = run('sch_inspect.py', sch)
        assert '封装完整 0 / 2' in out, out
        print('ok  sch_inspect：识别出 2 个缺封装的元件')
        check_footprints(sch, 'off=0（AD 导出约定）')

        sch2 = os.path.join(tmp, 'minimal_off-1.SchDoc')
        shift_owner_index(os.path.join(EXAMPLES, 'minimal.SchDoc'), sch2, -1)
        check_footprints(sch2, 'off=-1（自建文件约定）')

        pcb = os.path.join(tmp, 'minimal.PcbDoc')
        shutil.copy(os.path.join(EXAMPLES, 'minimal.PcbDoc'), pcb)
        out = run('pcb_inspect.py', pcb)
        assert '元件出板: 无' in out, out
        print('ok  pcb_inspect')
        out = run('pcb_place.py', pcb, '--blocks',
                  os.path.join(EXAMPLES, 'blocks.example.csv'), '--cols', '3', '--rows', '3')
        assert '出板 0 个' in out, out
        out = run('pcb_inspect.py', pcb)
        assert '元件出板: 无' in out, out
        print('ok  pcb_place + 复检：无元件出板')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('全部通过')


if __name__ == '__main__':
    main()
