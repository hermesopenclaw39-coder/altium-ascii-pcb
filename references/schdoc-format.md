# Altium ASCII SchDoc 格式笔记（以 AD 6.7 / Protel 5.0 为准）

## 容器

- 文件首行：`|HEADER=Protel for Windows - Schematic Capture Ascii File Version 5.0|WEIGHT=<n>`
- 之后每行一条记录：`|RECORD=<类型>|KEY=VALUE|KEY=VALUE...`
- 编码 **GBK**（中文图纸名、注释）。
- `WEIGHT` 的取值不统一：AD 导出常为 `记录数-1`，部分版本为 `记录数+1`。AD 不严格校验，但改动记录数后应同步更新。

## 常用记录类型

| RECORD | 含义 | 关键字段 |
|---|---|---|
| 1 | 元件 | `LIBREFERENCE` `LOCATION.X/Y` `ORIENTATION`（0/1/2/3，1=逆时针90°）`CURRENTPARTID` |
| 2 | 引脚 | `OWNERINDEX` `OWNERPARTID` `LOCATION.X/Y`（本体端）`PINLENGTH` `PINCONGLOMERATE`（低2位=方向 0右1上2左3下；bit3=隐藏；bit5=显示名称）`DESIGNATOR` `NAME` `ELECTRICAL` |
| 4 | 文本 | `LOCATION.X/Y` `TEXT` `FONTID` `COLOR` |
| 6 | 折线 | `LOCATIONCOUNT` `X1..Xn` `Y1..Yn` `ISSOLID` `AREACOLOR` `LINEWIDTH` |
| 12 | 圆弧 | `LOCATION.X/Y` `RADIUS` `STARTANGLE` `ENDANGLE` `LINEWIDTH` |
| 14 | 矩形 | `LOCATION.X/Y` `CORNER.X/Y` `ISSOLID` `AREACOLOR` |
| 25 | 网络标签 | `LOCATION.X/Y` `TEXT` `ORIENTATION` |
| 27 | 导线 | `X1 Y1 X2 Y2`（必须正交） |
| 29 | 连接点 | `LOCATION.X/Y` |
| 31 | 图纸 | `CUSTOMX/CUSTOMY` `BORDERON` `TITLEBLOCKON` `SHEETSTYLE` |
| 34 | 位号 | `OWNERINDEX` `TEXT`（真正的位号在这里）`NAME=Designator` |
| 41 | 参数 | `OWNERINDEX` `NAME`（如 `Comment`）`TEXT` |
| 44 | 实现列表 | `OWNERINDEX=<元件位置+off>` |
| 45 | 封装模型 | `OWNERINDEX=<44的位置+off>` `MODELNAME` `MODELTYPE=PCBLIB` `DATAFILECOUNT=1` `MODELDATAFILEENTITY0=<封装名>` `MODELDATAFILEKIND0=PCBLib` `ISCURRENT=T` `DESCRIPTION` |
| 46 / 48 | 45 的子记录 | `OWNERINDEX=<45的位置+off>` |

## 索引规则（最容易踩坑）

- **`OWNERINDEX = 父记录位置 + off`**。"位置"从表头（`|HEADER=` 那行）之后的第一条记录记为 0。
  - AD 6.7 自己导出的文件：`off = 0`（例如位号 34 的 `OWNERINDEX` 就等于它所属元件 `RECORD=1` 的位置，45 的 `OWNERINDEX` 等于 44 的位置）。
  - 手写或其他工具生成的文件可能是 `off = -1`。
  - **同一个文件里所有记录用同一个 `off`**。脚本用"位号 34 能否指回元件 1"来自动探测 `off`。
  结论：**插入记录后必须整表重映射**，不能局部打补丁。
- **`INDEXINSHEET` 在 AD 自己保存的文件里完全不存在**（实测 1469 条记录中 0 条带该字段）。自建文件若带该字段，追加时要用"记录总数"作为起点，否则会与已有值撞号，AD 报 `List index out of bounds (N)`。

## 一个元件的完整子记录顺序（AD 自己写的）

```
|RECORD=1|...|LIBREFERENCE=741_DIP8|...            ← 元件
|RECORD=34|OWNERINDEX=<元件>|TEXT=U1|NAME=Designator
|RECORD=41|OWNERINDEX=<元件>|TEXT=741|NAME=Comment
|RECORD=44|OWNERINDEX=<元件>                       ← 实现列表
|RECORD=45|OWNERINDEX=<44>|MODELNAME=DIP-8|MODELTYPE=PCBLIB|DATAFILECOUNT=1|MODELDATAFILEENTITY0=DIP-8|MODELDATAFILEKIND0=PCBLib|ISCURRENT=T
|RECORD=46|OWNERINDEX=<45>
|RECORD=48|OWNERINDEX=<45>
|RECORD=27|...                                     ← 之后的图元
```

**45/46/48 必须落在这段连续区域里**。追加到文件末尾会让 AD 在 `OpenObject` 阶段崩。

## 坐标与方向

- 单位：10 mil（1 unit = 0.01 inch）。整张图常用 100 mil 栅格。
- 引脚热端 = `LOCATION + PINLENGTH * dir(PINCONGLOMERATE & 3)`。
- 元件 `ORIENTATION=1` 时，子图元坐标已由 AD 写死为绝对坐标，**移动元件只需整体平移**，无需重算旋转。

## 库符号（SchLib / IntLib）里的记录

SchLib 与 SchDoc 共用同一套 RECORD 编号，但 SchLib 里：
- 每个 Part 有自己的 `Data` 流，记录从 `|RECORD=1|` 开始；
- 符号图形同样是 6/7/12/13/14 等记录；
- `RECORD=13` 是**单根直线**（`LOCATION` → `CORNER`），不是矩形；`RECORD=7` 是实心多边形。
- 从 IntLib 取符号：`olefile` 打开 → 读 `Library/Data`（必要时 `zlib.decompress(raw[1:])`）→ 按 `|RECORD=` 解析。
