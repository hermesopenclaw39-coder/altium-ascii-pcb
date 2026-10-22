# 会崩 AD 的写法与排查顺序

AD 6.7 遇到结构非法的 ASCII 文件**不报错，直接崩溃**。以下是实测过的三类崩溃与对应修法。

## 1. `Access violation ... in module 'AdvSch.dll' ... Exception Occurred In OpenObject`

**原因**：把 `RECORD=45/46/48`（封装）追加到了 SchDoc 文件末尾，脱离了元件的子记录块。
AD 在 `OpenObject` 阶段按"元件 → 子记录连续段"建对象，找不到归属就崩。

**修法**：把 45/46/48 **紧插在该元件的 `RECORD=44` 之后**，并重映射全表 `OWNERINDEX`。
见 `scripts/sch_add_footprints.py`。

## 2. `List index out of bounds (N) at 1005292E. AdvSch.dll`

**原因**：`INDEXINSHEET` 与 AD 内部列表长度不一致——要么新记录的编号撞了已有记录，要么超出列表末尾（AD 存的文件里根本没有这个字段）。

**修法**：不要写 `INDEXINSHEET`。若文件本身必须带，用"记录总数"作为起始编号，绝不能用"现有最大值 + 1"（有记录缺该字段时 max 偏小，必然撞号）。

## 3. `Access violation ... Read of address 00000006 at 0F675BE0. AdvSch.dll`

**原因**：同上第 1 类的另一种表现（父子记录脱节后解引用空指针）。

## 4. 打开后 PCB 里器件全是"空壳"（有位号没焊盘），ECO 报 `Unknown Pin: Pin C1-1`

**原因**：更新时原理图里的元件**没有封装模型**。AD 只能建出没有焊盘的元件。

**修法**：先确认原理图 `RECORD=45` 齐全（`sch_inspect.py` 的"封装完整 N/N"），再执行 `Design → Update PCB Document`。
另外注意：**工程里必须先存在一个 PcbDoc**，原理图的 `Design` 菜单才会出现 `Update PCB Document xxx` 这一项；否则只能从 PCB 侧走 `Design → Import Changes From <工程>`。

## 5. 差分对话框全是 "No Change"，但 PCB 是空的

**原因**：比较的是"另一个 SchDoc"（工程里有多张图时容易选错），或方向选反（PCB → 原理图）。

**修法**：`Show Differences` 里要选 **Schematic 在前、PCB 在后**；`Affected Document` 一列必须全是 PcbDoc。若出现 `Remove Pins From Net` 且 `Affected Document` 是 SchDoc，说明方向反了，**不要 Execute**，直接 Close。

## 6. 弹 `Match Nets` 配对对话框

**原因**：目标 PCB 里已经有别的网络，AD 怀疑是网络改名。

**修法**：两套电路不要配对，直接 Cancel；改用一块**全新的空 PCB** 做 Update，就不会弹。

## 排查顺序（省时间）

1. 文件是 ASCII 还是二进制？（首 6 字节 `|HEADE` / 首 8 字节 `D0CF11E0`）——二进制就别想脚本改了。
2. `sch_inspect.py` / `pcb_inspect.py` 先跑一遍，看记录数、WEIGHT、索引是否自洽。
3. 崩溃发生在"打开文件"阶段 → 查记录顺序与索引；发生在"Update PCB"阶段 → 查封装与工程里的 PcbDoc。
4. AD 崩了进程不退出：`Stop-Process -Name AD67 -Force`，然后**用管理员权限重启**（非管理员启动会报 `EOleException in AdvSch.dll`）。
