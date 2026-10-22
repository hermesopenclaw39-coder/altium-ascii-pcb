# altium-ascii-pcb

**[English](README.md)** | **简体中文**

> 用脚本读写 Altium Designer 的 ASCII 原理图（SchDoc）和 PCB（PcbDoc）：批量加封装、按分区摆器件、核对连通性，以及排查「AD 一打开就崩」的记录结构问题。
>
> Script-driven editing of Altium Designer ASCII schematics (`.SchDoc`) and PCBs (`.PcbDoc`) — batch footprint assignment, block placement, connectivity audit, and diagnosis of the record-structure bugs that crash AD on open.
>
> 本仓库同时是一个 **Agent Skill**：装进 Claude Code / WorkBuddy 后，AI 能直接读写你的 SchDoc / PcbDoc，而这些「一碰就崩」的规则已经写进技能里。

---

## 为什么会有这个项目

Altium 的 ASCII 导出是纯文本 `|KEY=VALUE|KEY=VALUE`，看起来很好处理，实际上**记录顺序和索引规则极其脆弱**：写错一个字段，AD 不报错，直接 `Access Violation` 崩掉，连崩溃点都只给你一个 `AdvSch.dll` 的地址。

这些都是实测踩出来的：

| 症状 | 真正的原因 |
|---|---|
| `Access violation ... Exception Occurred In OpenObject` | 把封装记录 `45/46/48` 追加到了文件末尾，脱离了元件的子记录块 |
| `List index out of bounds (N)` | `INDEXINSHEET` 与 AD 内部列表撞号——AD 自己存的文件里根本没有这个字段 |
| 打开后 PCB 里器件是空壳，ECO 报 `Unknown Pin: Pin C1-1` | 原理图元件没有封装模型，AD 只建出了没有焊盘的元件 |
| 差分对话框全是 `No Change`，但板子是空的 | 比较的是另一张 SchDoc，或方向反了（PCB → 原理图） |
| 弹 `Match Nets` 配对框 | 目标 PCB 里已有别的网络，AD 怀疑是网络改名；换一块空板即可 |

项目把这些规则和修法固化成了脚本和文档，省得每次都重新踩一遍。

## 功能

| 脚本 | 作用 |
|---|---|
| `scripts/sch_inspect.py` | 原理图体检：元件数、位号重复、**封装链完整性**、悬空引脚、导线数 |
| `scripts/sch_add_footprints.py` | **批量加封装**：把 `45/46/48` 插到元件 `44` 之后，并重映射全表 `OWNERINDEX` |
| `scripts/pcb_inspect.py` | PCB 体检：出板、外框重叠、**每个网络是否完全连通**、同层短路 |
| `scripts/pcb_place.py` | 按 `Designator,Block` 分区摆器件，按真实外框避让，位号自动移到元件上方 |

只依赖 Python 标准库（读 `.IntLib` 时需要 `olefile`）。

## 安装

本仓库是标准的 Agent Skill 结构（`SKILL.md` + `scripts/` + `references/`），支持 Skill 的智能体都能用。先克隆：

```bash
git clone https://github.com/hermesopenclaw39-coder/altium-ascii-pcb.git
```

再复制到对应的技能目录：

| 工具 | 目录 |
|---|---|
| Claude Code | `~/.claude/skills/altium-ascii-pcb/`（仅当前项目用：`.claude/skills/altium-ascii-pcb/`） |
| WorkBuddy | `~/.workbuddy-ai/skills/altium-ascii-pcb/` |
| Claude 应用 | 把仓库打成 zip，在设置的 Skills 里上传 |

```bash
# 例：Claude Code
mkdir -p ~/.claude/skills && cp -r altium-ascii-pcb ~/.claude/skills/
```

也可以当普通脚本直接用，不装技能也行：

```bash
python scripts/sch_inspect.py 原理图.SchDoc
```

## 快速开始

### 1. 原理图体检

```bash
$ python scripts/sch_inspect.py 原理图.SchDoc
文件 原理图.SchDoc
记录 1134 条，WEIGHT=1133 (一致)
元件 94 个，位号 94 个
重复位号: 无
封装完整 0 / 94，缺: ['VCC', 'RW1', 'R1', ...]
引脚 214 个，悬空 24 个
   U20      pin 1   @ (1620, 2150)
导线 259 段
```

### 2. 批量加封装

先写一份 `footprint_map.json`（键是元件的 `LIBREFERENCE`）：

```json
{
  "Resistor": "AXIAL-0.4",
  "Capacitor": "RAD-0.1",
  "741_DIP8": "DIP-8",
  "Header3": "HDR1X3"
}
```

```bash
$ python scripts/sch_add_footprints.py 原理图.SchDoc --map footprint_map.json
元件 94 个，已有封装 0 个，本次补 94 个
已备份 → 原理图.SchDoc.bak_fp
完成：1510 条记录，WEIGHT=1509。请用 sch_inspect.py 复检。
```

再跑一次 `sch_inspect.py`，应看到 `封装完整 94 / 94`。

### 3. PCB 体检

```bash
$ python scripts/pcb_inspect.py 板子.PcbDoc
记录 1656 条；元件 94，焊盘 214，网络 55，走线 385 段
板框 X 1044.4~8052.2  Y 1034.4~5168.2 mil
元件出板: 无
元件外框重叠: 2 对 [('U5', 'U4'), ('U4', 'TRI_OUT')]
完全连通网络: 20 个；不完整: 29 个
   GND              焊盘26 → 5 块
同层不同网络交叉（潜在短路）: 0 处 []
```

### 4. 按分区摆器件

`blocks.csv`：

```csv
Designator,Block
R1,A
R2,A
U1,B
```

```bash
$ python scripts/pcb_place.py 板子.PcbDoc --blocks blocks.csv --cols 3 --rows 3
摆放 94 个元件，出板 0 个 []
已写入 板子.PcbDoc（1656 条）。请用 pcb_inspect.py 复检。
```

`Block` 取 `A..I`，按阅读顺序「上→下、左→右」映射到 `cols × rows` 网格。

## 三条铁律

1. **子记录必须紧贴父记录。**
   SchDoc 里一个元件是连续的一段：
   `元件(1) → 位号(34) → 参数(41) → 实现列表(44) → 封装(45) → 46 → 48 → 后续图元`。
   把 `45` 追加到文件末尾 = AD 打开时崩在 `OpenObject`。

2. **插入记录后必须重映射全表 `OWNERINDEX`。**
   约定是 `OWNERINDEX = 父记录位置 + off`：位置从表头之后的第一条记为 0；`off` 在同一文件内固定（AD 直接导出的文件 `off=0`，自建文件可能是 `-1`），脚本会自动探测。

3. **AD 一旦保存就把 ASCII 转成二进制。**
   所有脚本改动都必须做在 AD 未保存的 ASCII 版本上；被 AD 存过之后只能重新 `Save As → ASCII` 导出。

## 不要尝试的事

- **不要脚本化 AD 的菜单**：AD 以管理员权限运行时，模拟按键/鼠标被 UIPI 拦截，菜单完全不响应，只有标准模态对话框能收 `{ENTER}`。
- **不要凭空写 `RECORD=Polygon`（铺铜）**：没有样本时字段猜错会把 GND 和其他网络短接。铺铜交给 AD 的 `Place → Polygon Pour`，它会按间距规则自动避让。
- **不要用自写布线器追求 100% 连通**：密集布局下迷宫布线只能到 70% 左右。正确做法是自己布一部分、剩下的交给 `Route → Auto Route → All`。

## 自测

```bash
python tests/test_examples.py
```

中文 Windows 的 GBK 控制台请先 `set PYTHONIOENCODING=utf-8`，否则中文输出会是乱码。

会在临时目录里对 `examples/` 下的最小原理图和 PCB 依次跑四个脚本，并检查批量加封装后复检为"封装完整"、重复运行不会重复插入。`examples/minimal.*` 是**手写的最小样例**，只用于测试解析逻辑，不保证能直接用 AD 打开；`examples/analog-reference.SchDoc` 则是**真实的 AD 6.7 导出文件**（94 个元件，姓名和学号已去掉），AD 能正常打开，测试里也会把它完整跑一遍。自己的项目请用 AD `Save As → ASCII` 导出。

## 支持版本

主要在 **Altium Designer 6.7**（Protel 5.0 格式）上实测。记录编号是 Protel/AD 的通用编号，较新版本大概率兼容，但字段可能有增减，遇到问题请附上文件头两行开 issue。

## 文档

- `references/schdoc-format.md` — 原理图记录格式、索引规则、SchLib 差异
- `references/pcbdoc-format.md` — PCB 记录格式、封装尺寸参考、从 IntLib 列封装名
- `references/pitfalls.md` — 6 类会崩 AD 的写法与排查顺序

## License

MIT
