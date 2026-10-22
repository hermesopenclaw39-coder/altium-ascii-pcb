# Altium ASCII PcbDoc 格式笔记（AD 6.7）

## 容器

- 文件由若干行 `|RECORD=<类型>|KEY=VALUE|...` 组成，**没有表头行**（第一条通常是 `|RECORD=Board|`）。
- 编码用 **latin-1** 解码：`FILENAME` 等字段里含 GBK 字节（中文路径），用 gbk 会抛 `UnicodeDecodeError`。
- 所有坐标带单位后缀：`X=1005mil`、`WIDTH=12mil`。读取时去掉末尾 `mil` 再转 float。

## 记录类型

| RECORD | 含义 | 关键字段 |
|---|---|---|
| Board | 板设置 | `ORIGINX/ORIGINY` `SNAPGRIDSIZE` `VISIBLEGRIDSIZE` `FILENAME` `KIND=Protel_Advanced_PCB` |
| Net | 网络 | `ID`（0 基自增）`NAME` `VISIBLE` `COLOR` |
| Component | 元件 | `ID` `X` `Y` `PATTERN`（封装名）`ROTATION` `LAYER=TOP` `SOURCEDESIGNATOR` `NAMEON` `COMMENTON` `SOURCEFOOTPRINTLIBRARY` `SOURCELIBREFERENCE` |
| Pad | 焊盘 | `NET` `COMPONENT` `NAME`（焊盘号）`X` `Y` `XSIZE` `YSIZE` `SHAPE` `HOLESIZE` `ROTATION` `LAYER=MULTILAYER` |
| Track | 走线/丝印线 | `LAYER`（`TOP` / `BOTTOM` / `TOPOVERLAY` / `KEEPOUT` / …）`X1 Y1 X2 Y2` `WIDTH` `NET`（布线的走线才有 NET） |
| Arc | 圆弧 | `LOCATION.X` `LOCATION.Y`（圆心）`RADIUS` `STARTANGLE` `ENDANGLE` `WIDTH` |
| Text | 文字 | `COMPONENT` `TEXT` `X` `Y` `HEIGHT` `LAYER` `ROTATION` |
| Fill | 实心矩形 | `X1 Y1 X2 Y2` `ROTATION` `LAYER` |
| Connection | 飞线（ratsnest） | `NET` `X1 Y1 X2 Y2` |
| Rule / DXPRule | 设计规则 | 名称与参数 |
| Class | 类 | `NAME` `KIND` |

## 元件与图元的归属

- 元件本身只有一条 `RECORD=Component`。
- **它的焊盘、丝印线、圆弧、位号文字、填充全部是独立记录**，通过 `COMPONENT=<元件ID>` 归属。
- 因此移动一个元件必须同时平移：`Pad` 的 `X/Y`、`Track`/`Fill` 的 `X1Y1X2Y2`、`Arc` 的 `LOCATION.X/Y`、`Text` 的 `X/Y`。
- 不属于任何元件的图元没有 `COMPONENT` 字段（如板框走线、布线走线）。

## 板框

板框通常是 **KeepOut 层**的一圈闭合走线：

```
|RECORD=Track|LAYER=KEEPOUT|X1=1044.3701mil|Y1=1034.3701mil|X2=8052.2441mil|Y2=1034.3701mil|WIDTH=10mil|...
```

四条线取包围盒即为板框。`Design → Board Shape → Define from selected objects` 用它生成实际板形。

## 封装尺寸参考（Miscellaneous Devices.IntLib，mil）

| 封装 | 宽 × 高 | 备注 |
|---|---|---|
| DIP-8 | 431 × 300 | 左右各 203~228 |
| VR3（电位器） | 300 × 1350 | 34mm 高，摆位必须单独占竖条 |
| AXIAL-0.4 | 80 × 400 | 卧式电阻 |
| RAD-0.1 | 200 × 200 | 瓷片电容 |
| CAPPR5-5x5 | 197 × 197 | 电解电容 |
| DO-35 | 75 × 280 | 二极管 |
| TO-92 | 185 × 185 | 三极管 |
| PIN1 | 141 × 141 | 测试点 |
| HDR1X2 / HDR1X3 | 100 × 200 / 100 × 300 | 排针 |

## 从 IntLib 里列封装名

```python
import olefile, zlib, io
o = olefile.OleFileIO(r'...\Miscellaneous Devices.IntLib')
raw = o.openstream('PCBLib/0.pcblib').read()
o2 = olefile.OleFileIO(io.BytesIO(zlib.decompress(raw[1:])))   # 跳过 1 字节前缀
names = sorted({e[0] for e in o2.listdir() if len(e) == 2 and e[1] == 'Data'})
```

Devices 库有 155 个封装，Connectors 库有 183 个（含 `HDR1X2`~`HDR1X25`）。

## 布线

- 走线记录必须带 `NET=<网络ID>`，否则视为"自由走线"，不参与连通性。
- 两层板可用"每网络固定一层"策略：跨层交叉不算冲突，且通孔焊盘本身连接两层，**无需过孔**即可从任一层的焊盘起线。
- `RECORD=Via`（过孔）的字段没有可靠样本时不要臆造。
- `RECORD=Polygon`（铺铜）字段复杂且会按间距规则自动避让，**不要手写**；交给 AD 的 `Place → Polygon Pour`。
