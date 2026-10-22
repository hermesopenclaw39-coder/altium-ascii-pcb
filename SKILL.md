---
name: altium-ascii-pcb
description: Reads, audits and edits Altium Designer ASCII schematic (SchDoc) and PCB (PcbDoc) files programmatically - batch-assigning PCB footprints to schematic components, placing components on a board, checking pin/net connectivity, and diagnosing AD crashes caused by malformed records. This skill should be used when a task involves 批量给原理图加封装、按坐标摆板、核对原理图/PCB 连通性，或 AD 打开文件即崩溃并报 "List index out of bounds" / "Access violation in AdvSch.dll" / "Exception Occurred In OpenObject"，尤其是 AD 6.7 / Protel 99SE 等老版本。
---

# Altium ASCII SchDoc / PcbDoc Toolkit

Altium Designer 的 ASCII 导出格式是 `|KEY=VALUE|KEY=VALUE` 的纯文本，可以脚本化读写。但它的**记录顺序与索引规则极其脆弱**：写错一个字段 AD 不报错，而是直接 Access Violation 崩溃退出。本技能沉淀了逆向出来的格式规则、可复用脚本、以及会崩 AD 的具体陷阱。

## 何时使用

- 需要给几十上百个原理图元件批量指定封装（`RECORD=45`）
- 需要按坐标批量摆放 PCB 器件、核对布局是否出界/重叠
- 需要检查原理图引脚是否悬空、PCB 网络是否全部连通、有没有同层短路
- AD 打开某个 SchDoc/PcbDoc 就崩，报 `Access violation in AdvSch.dll` / `List index out of bounds (N)` / `Exception Occurred In OpenObject`

## 铁律（违反必崩 AD）

1. **子记录必须紧贴父记录**。SchDoc 里元件的子记录是连续的一段：
   `元件(1) → 位号(34) → 参数(41) → 实现列表(44) → 封装(45) → 46 → 48 → 后续图元`。
   把 45 追加到文件末尾 = AD 打开时崩在 `OpenObject`。
2. **插入记录后必须重算全表 OWNERINDEX**。约定是 `OWNERINDEX = 父记录位置 + off`：位置从表头（`|HEADER=`）之后的第一条记为 0；`off` 在同一文件内固定，AD 6.7 导出的文件为 0，自建文件可能是 -1。插入会让后面所有位置后移，必须整表重映射。脚本会自动探测 `off`。
3. **AD 自己存的文件里没有 `INDEXINSHEET`**。不要自己加，加了会与内部列表冲突（`List index out of bounds`）。若文件本身带该字段，追加时按"记录总数"往后编，**绝不能用"现有最大值+1"**——有记录缺该字段时 max 会偏小，导致撞号。
4. **AD 一旦保存就把 ASCII 转成二进制**。脚本改动必须在 AD 未保存的 ASCII 版本上做；被 AD 存过之后只能请用户重新 `Save As → ASCII` 导出。
5. **PcbDoc 的封装图元是独立记录**，用 `COMPONENT=<元件ID>` 归属。移动元件必须同步平移它的 Pad/Track/Arc/Text/Fill，否则焊盘留在原地、元件"散架"。

## 标准工作流

### A. 给原理图批量加封装

```bash
# 1) 体检：元件、位号、已有封装、悬空脚
python scripts/sch_inspect.py 原理图.SchDoc

# 2) 最稳的格式来源：在 AD 里手动给一个元件设好封装 → File → Save As →
#    Advanced Schematic ascii (*.SchDoc)，用这份文件当"格式样本"再批量补

# 3) 批量补：把 45/46/48 插到元件 44 之后，并重映射全表 OWNERINDEX
python scripts/sch_add_footprints.py 原理图.SchDoc --map footprint_map.json

# 4) 复检，确认 "封装完整 94/94"
python scripts/sch_inspect.py 原理图.SchDoc
```

`footprint_map.json` 形如 `{"Resistor": "AXIAL-0.4", "Capacitor": "RAD-0.1", "741_DIP8": "DIP-8"}`，键是元件的 `LIBREFERENCE`。

### B. 核对 PCB

```bash
python scripts/pcb_inspect.py 板子.PcbDoc
```

输出：元件/焊盘/网络数、元件是否出板、外框重叠对、走线是否出板、**每个网络是否完全连通**、**同层不同网络交叉（潜在短路）**。

### C. 按分区摆放器件

```bash
# blocks.csv 两列：Designator,Block   （Block 取 A..I，按阅读顺序上→下、左→右）
python scripts/pcb_place.py 板子.PcbDoc --blocks blocks.csv --cols 3 --rows 3
```

脚本按每个元件的**真实外框**（Pad/Track/Arc/Fill，不含位号文字）计算占位：高件（如 34mm 电位器）单独占竖条，其余自适应列数，保证不出板框；并把位号文字移到元件正上方、隐藏注释。

## 格式速查

| 对象 | 关键字段 |
|---|---|
| SchDoc 元件 | `RECORD=1｜LIBREFERENCE｜LOCATION.X/Y｜ORIENTATION` |
| SchDoc 位号 | `RECORD=34｜OWNERINDEX｜TEXT｜NAME=Designator` |
| SchDoc 封装 | `RECORD=45｜OWNERINDEX=44的位置+off｜MODELNAME｜MODELTYPE=PCBLIB｜DATAFILECOUNT=1｜MODELDATAFILEENTITY0=封装名｜MODELDATAFILEKIND0=PCBLib｜ISCURRENT=T` |
| PcbDoc 元件 | `RECORD=Component｜ID｜X=..mil｜Y=..mil｜PATTERN｜ROTATION｜SOURCEDESIGNATOR` |
| PcbDoc 焊盘 | `RECORD=Pad｜NET｜COMPONENT｜NAME｜X｜Y｜XSIZE｜HOLESIZE` |
| PcbDoc 走线 | `RECORD=Track｜LAYER=TOP/BOTTOM｜X1｜Y1｜X2｜Y2｜WIDTH｜NET` |
| PcbDoc 圆弧 | `RECORD=Arc｜LOCATION.X/Y｜RADIUS` |
| PcbDoc 填充 | `RECORD=Fill｜X1｜Y1｜X2｜Y2｜ROTATION` |

坐标一律带 `mil` 后缀（如 `1005mil`）。字段全集见 `references/schdoc-format.md`、`references/pcbdoc-format.md`。

## 不要尝试的事

- **不要脚本化 AD 的菜单**：AD 以管理员权限运行时，模拟按键/鼠标被 UIPI 拦截，菜单完全不响应（`SendKeys "^o"`、`Alt+F` 均无效），只有标准模态对话框能收 `{ENTER}`。
- **不要凭空写 `RECORD=Polygon`（铺铜）**：没有样本时字段猜错会把 GND 与其他网络短接。让用户在 AD 里 `Place → Polygon Pour` 三步完成，AD 会按间距规则自动避让。
- **不要用自写布线器追求 100% 连通**：密集布局下迷宫布线只能到 70% 左右。正确做法是自己布一部分、剩下交给 `Route → Auto Route → All`（它会避开已有走线）。
- **不要在 AD 打开文件时覆盖写**：先让用户关闭文档，或提醒它会弹"文件已被修改"需要重载。

## 环境注意

- 读写编码：SchDoc 用 `gbk`；PcbDoc 用 `latin-1`（其路径字段含 GBK 字节，用 gbk 会解码失败）。
- IntLib 里的 PCB 封装名：`olefile` 打开 `.IntLib` → 读 `PCBLib/0.pcblib` → `zlib.decompress(raw[1:])` → 再用 `olefile` 打开解压结果 → **带 `Data` 子流的存储名就是封装名**。
- AD 6.7 崩溃后进程不退出，需 `Stop-Process -Name AD67 -Force` 才能重启。
- 复核脚本依赖标准库即可，无需第三方包（olefile 除外，仅在读 IntLib 时用）。
