# EP4CE6 Bitstream 逆向工程

## 这是什么项目？

这个项目的目标是**完全逆向工程** Altera（现 Intel）Cyclone IV 系列 FPGA 芯片 **EP4CE6F17C8** 的比特流（bitstream）格式。

### 什么是 FPGA？

FPGA（Field-Programmable Gate Array，现场可编程门阵列）是一种可以通过编程来实现任意数字电路的芯片。和 CPU 不同，FPGA 不是执行"指令"——而是直接在硬件层面"搭建"电路。你可以把它想象成一块巨大的面包板，上面有成千上万个可编程的逻辑门和连线，你通过一个配置文件来决定这些门和连线怎么连接。

这个"配置文件"就叫做 **bitstream**（比特流），对于 Altera 芯片来说，具体格式是 `.rbf`（Raw Binary File）。

### 为什么要逆向比特流？

商业 FPGA 厂商（Intel/Altera、Xilinx/AMD）的比特流格式是**不公开的**。你必须使用他们的专有工具（如 Quartus）来生成比特流。这意味着：

1. **没有开源工具链**：你不能用开源的综合器（如 Yosys）和布局布线器（如 NextPNR）来完成从 Verilog 到比特流的完整流程
2. **无法理解芯片内部**：不知道比特流的每一个 bit 控制着芯片的哪个部分
3. **依赖闭源软件**：Quartus 是免费但不开源的，且只支持特定操作系统

逆向比特流格式后，我们就能：
- 为 EP4CE6 构建完全开源的 FPGA 工具链
- 理解芯片内部的 CRAM（Configuration RAM）是如何组织的
- 直接读写比特流中的逻辑配置和布线信息

### 先驱项目

| 项目 | 目标芯片 | 方法 | 与本项目关系 |
|------|----------|------|-------------|
| [Project IceStorm](http://www.clifford.at/icestorm/) | Lattice iCE40 | 黑箱 fuzzing | 方法论完全相同 |
| [Project X-Ray](https://github.com/SymbiFlow/prjxray) | Xilinx 7-series | Vivado + specimen fuzzing | FASM 格式可参考 |
| [Project Mistral](https://github.com/Ravenslofty/mistral) | Altera Cyclone V | quartus_cdb + Tcl | 同家族芯片，参考价值最高 |
| [Project Trellis](https://github.com/YosysHQ/prjtrellis) | Lattice ECP5 | Diamond + fuzzing | 布线策略可参考 |

---

## 硬件和软件环境

### 硬件

- **开发板**：黑金 AX301
- **FPGA 芯片**：EP4CE6F17C8（Cyclone IV E 系列，6,272 个逻辑单元）
- **编程器**：USB-Blaster JTAG

### 软件

- **Quartus Prime 21.1 Lite Edition**：Intel 免费提供的 FPGA 开发工具
  - 安装路径：`~/intelFPGA_lite/21.1/quartus/bin/`
  - 用到的命令行工具：`quartus_map`（综合）、`quartus_fit`（布局布线）、`quartus_asm`（生成 .sof）、`quartus_cpf`（转换为 .rbf）、`quartus_sta`（静态时序分析）
- **openFPGALoader**：开源的 FPGA 编程工具（烧写比特流到板子上）；使用 `$HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader`，系统自带版本无法识别 EP4CE6 的 IDCODE
- **Python 3**：fuzzing 脚本全部用 Python 编写
- **SQLite**：存储实验结果的数据库

### EP4CE6 芯片几何结构

```
EP4CE6F17C8 内部布局（简化示意）：

     X=3  4  6  7  8  10 11 12 13  16 17 18 19  21 22 23 24 25 26  28 29 31
Y=21 [LAB][LAB][LAB][LAB][LAB][LAB]...                                [LAB]
Y=19 [LAB][LAB][LAB][LAB][LAB][LAB]...                                [LAB]
 ...    |    |    |    |    |    |                                       |
Y=2  [LAB][LAB][LAB][LAB][LAB][LAB]...                                [LAB]
          ^         ^              ^                    ^
          X=5       X=9            X=14-15              X=20,27
          M9K       M9K            DSP                  M9K
          RAM       RAM            乘法器               RAM
```

- **392 个 LAB**（Logic Array Block），每个 LAB 包含 **16 个 LE**（Logic Element）
- **LAB X 坐标**：22 个值 `[3, 4, 6, 7, 8, 10, 11, 12, 13, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 28, 29, 31]`
  - 注意 X 坐标不连续！X=5, 9, 14, 15, 20, 27, 30 是 M9K 存储器、DSP 乘法器或 PLL 的位置
- **LAB Y 坐标**：18 个值 `[2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 21]`
  - Y=15 和 Y=20 不存在（CRAM 中的"幽灵行"）
- **LE N 索引**：16 个偶数值 `[0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]`
- **总计**：392 × 16 = **6,272 个 LE**

每个 LE 包含：
- 一个 **4 输入查找表**（LUT4）：可实现任意 4 变量布尔函数
- 一个 **D 触发器**（DFF）：可选使用
- 进位链逻辑（用于加法器等算术运算）

---

## 核心方法论："Pair-Diff"（配对差分法）

这是整个逆向工程的核心方法，简单而强大：

### 基本思想

> 如果你想知道比特流中的哪些 bit 控制着某个特定功能，那就编译两个**只在这个功能上有差别**的设计，然后比较它们的比特流。差异的 bit 就是控制这个功能的 bit。

### 具体步骤（以 LUT 真值表为例）

```
步骤 1: 编译一个 LUT，真值表设为全 0（mask = 0x0000）
        → 得到 zero.rbf

步骤 2: 编译相同位置的 LUT，真值表设为全 1（mask = 0xFFFF）
        → 得到 ones.rbf

步骤 3: 逐 bit 比较 zero.rbf 和 ones.rbf
        → 差异就是这个 LE 的真值表 CRAM 位
```

### 为什么这样做有效？

因为两个设计除了 LUT 的真值表不同之外，其他一切——布线、IO 缓冲区、全局配置——都完全一样。所以差异的 bit **只能是**真值表的编码。

### 对比方法的层次

| 方法 | 对比对象 | 效果 | 噪声 |
|------|----------|------|------|
| 设计 vs 空白 | 有功能 vs 无功能 | 找到所有相关 bit | 高（包含布线等） |
| Pair-diff | mask=0x0000 vs mask=0xFFFF | 只找到 LUT TT bit | **零噪声** |
| 多掩码交叉 | 多个不同 mask 的设计 | 验证 XOR 线性模型 | 零 |

### 代码中如何实现？

```python
# rbf_diff.py — 比较两个 RBF 文件
def diff_rbf(rbf_a: bytes, rbf_b: bytes) -> list[BitDiff]:
    diffs = []
    for i in range(RBF_SIZE):           # 遍历 368,011 个字节
        xor = rbf_a[i] ^ rbf_b[i]      # XOR 找出不同的字节
        if xor:
            for bit in range(8):        # 检查每个 bit
                if xor & (1 << bit):
                    direction = 1 if (rbf_b[i] >> bit) & 1 else -1
                    diffs.append(BitDiff(i, bit, direction))
    return diffs
```

每个 `BitDiff` 记录三个信息：
- `byte_offset`：在 RBF 文件中的字节偏移量（0 到 368,010）
- `bit_position`：在该字节中的 bit 位置（0=最低位，7=最高位）
- `direction`：变化方向（+1 表示 0→1，-1 表示 1→0）

---

## RBF 文件格式

EP4CE6 的 RBF 文件总是恰好 **368,011 字节**，不管设计多复杂：

```
┌──────────────────────────┐
│  前导 (Preamble)          │  32 字节，全部为 0xFF
├──────────────────────────┤
│                          │
│  配置数据 (Config Data)    │  367,920 字节
│  包含 CRAM 内容            │  这里面编码了所有的逻辑和布线
│                          │
├──────────────────────────┤
│  尾部 (Postamble)         │  59 字节，全部为 0xFF
└──────────────────────────┘
```

**关键区域：**
- `0x0020 - 0x0028`：设备头（常量：`6A F7 F7 F7 F7 F7 F7 F3 FB`）
- `0x0029 - 0x0034`：设计相关数据（12 字节，可能是资源使用编码）
- `0x0049 - 0x004A`：CRC/校验和（每次修改都会变）
- `0x004B - 0x59BBB`：CRAM 配置数据主体

---

## 项目目录结构

```
EP4CE6/
├── README.md               ← 你正在读的文件
├── CLAUDE.md               ← AI 助手的上下文记忆文件
├── fuzz/                   ← Fuzzing 管线（Python 源代码）
│   ├── config.py           ← EP4CE6 常量、坐标、引脚定义
│   ├── verilog_gen.py      ← Verilog 代码生成器
│   ├── qsf_gen.py          ← Quartus 工程配置文件生成器
│   ├── compile.py          ← Quartus 无头编译驱动
│   ├── rbf_diff.py         ← Bit 级二进制差分引擎
│   ├── database.py         ← SQLite 数据库接口
│   ├── runner.py           ← Fuzzing 实验编排器（主入口）
│   ├── analyze.py          ← 结果分析和可视化
│   └── bitstream.py        ← Bitstream 编解码器（读/写 LUT、路由开关）
├── results/
│   ├── rbf/                ← 收集的 .rbf 文件（~850 个，各 368 KB）
│   ├── ep4ce6_bitdb.sqlite ← Bit 映射数据库（569K 条记录）
│   └── FINDINGS.md         ← 详细发现报告
├── work/                   ← Quartus 临时编译目录（可清理）
├── work_route/             ← 路由实验编译目录
└── work_verify/            ← 验证实验编译目录
```

### 源代码统计

| 文件 | 行数 | 功能 |
|------|------|------|
| `config.py` | 160 | 芯片常量、CRAM 地址公式、引脚定义 |
| `verilog_gen.py` | 193 | 8 个 Verilog 生成函数 |
| `qsf_gen.py` | 80 | QSF 项目配置生成 |
| `compile.py` | 269 | Quartus 编译流程驱动 + STA 路由提取 |
| `rbf_diff.py` | 110 | 二进制比较引擎 |
| `database.py` | 192 | SQLite 数据库操作 |
| `runner.py` | 1,226 | 实验编排器（最大的文件） |
| `analyze.py` | 569 | 分析、可视化和编解码命令 |
| `bitstream.py` | 614 | **Bitstream 编解码器（LUT + 路由读/写）** |
| **总计** | **~3,413** | |

---

## 代码架构详解

### 1. `config.py` — 芯片常量

这个文件定义了 EP4CE6 的所有物理参数：

```python
# 芯片几何
LAB_X = [3, 4, 6, 7, 8, 10, 11, 12, 13, 16, 17, 18, 19, 21, ...]  # 22 个 LAB 列
LAB_Y = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, ...]     # 18 个 LAB 行
LE_N  = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]  # 16 个 LE

# CRAM 列基地址（22 列，每列的起始位置不同）
COLUMN_BASE = {
    3: 0x076E0,   # 第一个 LAB 列
    4: 0x09396,   # = 0x076E0 + 7350 (标准步长)
    6: 0x0CD02,   # = 0x09396 + 14700 (跳过 M9K 列)
    ...
}

# 引脚分配（对应 AX301 开发板的 GPIO）
FUZZ_PINS = {
    "A": "PIN_E16",   # 按键 KEY2 → LUT 输入 A
    "B": "PIN_M16",   # 按键 KEY3 → LUT 输入 B
    "C": "PIN_M15",   # 按键 KEY4 → LUT 输入 C
    "D": "PIN_E15",   # 复位键    → LUT 输入 D
    "Q": "PIN_G15",   # LED[0]    → LUT 输出
}
```

最重要的是 **CRAM 地址模型**函数：

```python
def cram_ctrl_addr(x, y, pair, n=0):
    """计算 (X, Y, N) 位置的 LUT TT 第 pair 对的 CRAM 控制字节地址"""
    cram_row = y - 2          # Y 坐标映射到 CRAM 行号
    slot = cram_row % 3       # 3 行一组，slot=0,1,2
    group = cram_row // 3     # 第几组（0~6）
    # ... 计算偏移量
```

### 2. `verilog_gen.py` — Verilog 生成器

生成极简的 Verilog 设计，每个设计只包含一到两个 LUT：

```python
def gen_lut4_primitive(mask: int) -> str:
    """使用 Cyclone IV 原语直接实例化一个 LUT，控制其 16 位真值表"""
    return f"""
    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask:04X}),     // 真值表，如 0x8888 = A & B
        .dont_touch("on")              // 告诉 Quartus 不要优化掉它
    ) lut_inst (
        .dataa(A), .datab(B), .datac(C), .datad(D),
        .combout(lut_out)
    );"""
```

**为什么用原语（primitive）而不是行为级描述？**

行为级（`assign Q = A & B;`）让 Quartus 决定怎么实现你的逻辑，综合器可能优化、合并或重排 LUT。而直接实例化 `cycloneive_lcell_comb` 原语，你可以精确控制 16 位真值表的每一个 bit，这对逆向工程至关重要。

**可用的生成器函数：**

| 函数 | 用途 | 说明 |
|------|------|------|
| `gen_lut4(expr)` | 行为级 LUT | 用布尔表达式描述 |
| `gen_lut4_primitive(mask)` | 原语级 LUT | 精确控制真值表 |
| `gen_two_luts_primitive(m1, m2)` | 两个相连的 LUT | 用于布线 fuzzing |
| `gen_single_lut_primitive_extra_inputs(m)` | 单 LUT + 7 输入端口 | 布线 fuzzing 的基线 |
| `gen_lut4_ff(expr)` | LUT + 触发器 | 用于 DFF fuzzing |
| `gen_empty()` | 空设计 | 全局基线 |

### 3. `qsf_gen.py` — QSF 生成器

QSF（Quartus Settings File）是 Quartus 的工程配置文件。这个模块生成 QSF 并加入关键的设置：

```python
# 关闭所有优化 — 这是 fuzzing 能成功的关键！
QSF_OPTIMIZATIONS_OFF = [
    ('AUTO_RAM_RECOGNITION', 'OFF'),          # 不自动推断 RAM
    ('AUTO_DSP_RECOGNITION', 'OFF'),          # 不自动推断 DSP
    ('AUTO_SHIFT_REGISTER_RECOGNITION', 'OFF'),# 不自动推断移位寄存器
    ('SYNTH_TIMING_DRIVEN_SYNTHESIS', 'OFF'),  # 不做时序驱动综合
    ('ROUTER_TIMING_OPTIMIZATION_LEVEL', 'MINIMUM'),  # 最小化布线优化
    ...
]

# 强制放置 LUT 到指定位置
placement = {"lut_inst": "LCCOMB_X10_Y10_N0"}
# 生成的 QSF 中会包含：
# set_location_assignment LCCOMB_X10_Y10_N0 -to "lut_inst"
```

**为什么要关闭优化？** 因为 Quartus 的优化器会改变布线路径。如果两次编译相同设计但优化器选择了不同路径，我们的 diff 就会包含布线噪声。设置 `ROUTER_TIMING_OPTIMIZATION_LEVEL MINIMUM` 后，布线变得**完全确定性**——相同的设计总是产生完全相同的比特流。

### 4. `compile.py` — Quartus 编译驱动

封装了 Quartus 的命令行工具链：

```
Quartus 编译流程：

Verilog    quartus_map    quartus_fit    quartus_asm    quartus_cpf
源代码  ──────────────► ──────────────► ──────────────► ──────────────►  .rbf
           (综合)         (布局布线)       (生成 .sof)     (转为 .rbf)
```

关键实现细节：

```python
def compile_and_export(project_name, verilog, qsf, rbf_output):
    """一站式：创建项目 → 编译 → 导出 RBF"""
    proj_dir = setup_project(project_name, verilog, qsf)  # 写入文件
    ok, elapsed, err = compile_full(project_name, proj_dir)  # 运行 Quartus
    if ok:
        rbf = generate_rbf(project_name, proj_dir, rbf_output)  # .sof → .rbf
    return rbf, elapsed, err

def extract_routing(project_name, proj_dir):
    """通过静态时序分析提取布线路径"""
    # 运行 Tcl 脚本调用 report_timing -show_routing
    # 解析输出得到每条路径经过的线网名称
```

**重要**：生成 RBF 必须用 `quartus_cpf -c -o bitstream_compression=off`，不能用 `sof2rbf.py`（后者会产生无效的比特流）。

### 5. `runner.py` — Fuzzing 实验编排器

这是最大的文件（~1,226 行），负责编排所有的 fuzzing 实验。主要命令：

```bash
# 生成基线 RBF
python3 runner.py baseline

# 对单个 LE 位置做 LUT 真值表 fuzzing
python3 runner.py --node lut_inst lut_single 10 10 0
# 参数：X=10, Y=10, N=0

# 扫描所有 16 个 minterm（单比特真值表模式）
python3 runner.py n_sweep 10 10

# 网格扫描所有 22 列的 pair-diff
python3 runner.py pair_diff_grid

# 并行布线 fuzzing
python3 runner.py route_map_parallel 10 5 col
# 参数：源 X=10, 源 Y=5, 方向=列（column）

# 批量布线 fuzzing（多个源位置）
python3 runner.py route_map_batch --sources 4,10 29,10 10,17 --direction row --jobs 4
```

### 6. `database.py` — SQLite 数据库

所有实验结果存储在 SQLite 数据库中：

```sql
-- 实验记录
CREATE TABLE experiments (
    id INTEGER PRIMARY KEY,
    name TEXT,                -- 实验名称，如 "lut_single_X10_Y10_N0"
    verilog TEXT,             -- Verilog 源代码（完整保存）
    qsf_placement TEXT,       -- 放置约束
    compile_time REAL,        -- 编译耗时（秒）
    rbf_path TEXT             -- RBF 文件路径
);

-- Bit 映射（核心数据）
CREATE TABLE bit_mapping (
    x INTEGER,                -- LAB X 坐标
    y INTEGER,                -- LAB Y 坐标
    n INTEGER,                -- LE 索引
    feature TEXT,             -- 功能名称，如 "lut_tt_0x0001"
    byte_offset INTEGER,      -- RBF 中的字节偏移
    bit_position INTEGER,     -- 字节内的 bit 位置
    direction INTEGER,        -- 变化方向 (+1 或 -1)
    PRIMARY KEY (x, y, n, feature, byte_offset, bit_position)
);

-- 布线路径
CREATE TABLE routing_paths (
    src_x, src_y, src_n,      -- 源 LE 坐标
    dst_x, dst_y, dst_n,      -- 目标 LE 坐标
    path_json TEXT             -- 线网路径（JSON 格式）
);
```

截至目前的数据库统计：
- **1,755** 次实验
- **609,835** 条 bit 映射记录
- **774** 条布线路径（含 STA 提取的完整线网路径）
- **95** 种不同的 feature

---

## 逆向工程成果：逐阶段详解

### Phase 1：搭建 Fuzzing 管线

**目标**：搭建自动化的编译→比较→记录流程。

**验证标准**：能够在指定坐标放置 LUT，编译出 RBF，并找到两个不同设计之间的 bit 差异。

**关键步骤**：

1. **编译空设计** → 得到 `baseline.rbf`（所有 LUT 功能为"不存在"时的比特流）
2. **在 (X=10, Y=10, N=0) 放置一个 `A & B` LUT** → 得到 `and.rbf`
3. **Diff** → 发现约 450 个 bit 差异（包括 LUT 配置 + 布线）
4. **用 Pair-Diff**：在同一位置放 mask=0x0000 和 mask=0xFFFF → 只差 64 个 bit → 这就是纯粹的 LUT 真值表！

**单次编译耗时**：~9-10 秒（综合+布局布线+生成 RBF），吞吐量 ~360-400 次/小时。

---

### Phase 2：破解逻辑配置

#### Phase 2.1：LUT 真值表编码

**发现**：LUT 真值表使用 **XOR 线性编码**。

这是什么意思？先看一个简化的例子：

假设一个 2 输入 LUT 有 4 个真值表 bit（TT[0] 到 TT[3]）。如果编码是"直接的"，那每个 TT bit 对应一个 CRAM bit。但 Cyclone IV 的编码更复杂——每个 TT bit 映射到 **8-10 个 CRAM 位**，而且这些 CRAM 位之间有 XOR 关系。

```
单 bit 模式（minterm 差分得到的 CRAM 位）：

TT bit 0 (mask 0x0001) → {A1, B3, B5, C2, C7, D1, D4, E6}  ← 8 个 CRAM 位
TT bit 1 (mask 0x0002) → {A1, B3, B5, C2, C7, D2, D5, E7}  ← 同样 8 个
                          ↑ ↑  ↑  ↑  ↑                        5 个共享！
                          这些位是两个 bit 共享的

任意 mask 的 CRAM 位 = XOR(各个为 1 的 TT bit 的 CRAM 位集合)
例如：mask 0x0003 (bit 0 和 bit 1 都为 1)
     = {A1,B3,B5,C2,C7,D1,D4,E6} XOR {A1,B3,B5,C2,C7,D2,D5,E7}
     = {D1,D2,D4,D5,E6,E7}  ← 共享的位 XOR 消掉了
```

**验证**：用多种 mask（0xFFFF, 0x8888, 0x6996 等）编译，XOR 线性预测与实际 diff **完全一致**。

#### 真值表的 CRAM 结构

每个 LE 的 16 位真值表编码在 **8 对 CRAM 字节**中：

```
每对 (pair) 包含：
  ┌─────────────────────────────┐
  │ ctrl_lo (1 byte)  ← 控制字节（低），标识 Y 行和 TT bit 编号 │
  │ ctrl_hi (1 byte)  ← 控制字节（高），紧挨着 ctrl_lo         │
  │ data_0  (1 byte)  ← 数据字节 0，在 ctrl 后面 +48 字节处    │
  │ data_1  (1 byte)  ← 数据字节 1，紧挨着 data_0              │
  └─────────────────────────────┘
  
  ctrl → data 偏移：48 字节（固定）
  pair → pair 间距：210 字节（固定）
  
  8 对 × 210 字节 ≈ 1,518 字节的 CRAM 跨度
```

**配对映射**（pair 编号 → TT bit 编号）：
```
Pair 0: TT[7]  (lo byte), TT[15] (hi byte)
Pair 1: TT[6]  (hi byte), TT[14] (lo byte)
Pair 2: TT[5]  (lo byte), TT[13] (hi byte)
Pair 3: TT[4]  (hi byte), TT[12] (lo byte)
Pair 4: TT[3]  (lo byte), TT[11] (hi byte)
Pair 5: TT[2]  (hi byte), TT[10] (lo byte)
Pair 6: TT[1]  (lo byte), TT[9]  (hi byte)
Pair 7: TT[0]  (hi byte), TT[8]  (lo byte)

公式：pair = 7 - (bit % 8)，字节侧交替
```

#### Phase 2.2：CRAM 地址模型（已验证 376/376 个位置，100%）

这是整个逆向工程中最核心的发现——我们找到了从 (X, Y, N) 坐标到 CRAM 字节地址的**完整映射公式**。

##### 列基地址

比特流按列组织，每个 LAB 列占据连续的 CRAM 区域：

```
标准 LAB 列宽度：7,350 字节 (0x1CB6)

   列 X=3      列 X=4      列 X=6      列 X=7
 ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
 │  7,350  │ │  7,350  │ │  7,350  │ │  7,350  │ ...
 │  bytes  │ │  bytes  │ │  bytes  │ │  bytes  │
 └─────────┘ └─────────┘ └─────────┘ └─────────┘
  0x076E0     0x09396     0x0CD02     0x0E9B8
              +7,350      +14,700     +7,350
                          (跳过 M9K)
```

非标准列宽出现在特殊资源边界：
- **M9K RAM**（X=5, 9, 20, 27, 30）：需要额外空间
- **DSP 乘法器**（X=14-15）：巨大的 CRAM 区域（76,230 字节跳跃）
- **PLL**：在 X=27 附近

##### Y 地址公式（slot/group 编码）

这是最精巧的部分。18 个 Y 坐标不是简单地映射到连续地址，而是使用一种"三行交织"的编码：

```python
cram_row = Y - 2              # Y=2 → 0, Y=3 → 1, ..., Y=21 → 19
slot  = cram_row % 3           # 每 3 行一组，slot 取 0, 1, 2
group = cram_row // 3          # 组号，0 到 6

# slot 决定基础偏移
SLOT_BASE = {0: 136, 1: 0, 2: 70}  # 字节

# group 决定精细偏移和 bit 位置
byte_offset = SLOT_BASE[slot] + group * 3
bit_position = 7 - group - (1 if slot > 0 else 0)
```

为什么是这种看起来很复杂的编码？因为 Cyclone IV 的 CRAM 物理上是按行扫描的，每个 CRAM 字节需要同时为多个 Y 行的开关服务。`slot` 决定了物理位置，`group` 决定了字节内的哪个 bit。

**完整 Y 映射表**：

| Y | slot | group | 字节偏移 | bit 位 | 说明 |
|---|------|-------|---------|--------|------|
| 2 | 0 | 0 | +136 | bit-7 | 底边 |
| 3 | 1 | 0 | +0 | bit-6 | |
| 4 | 2 | 0 | +70 | bit-6 | |
| 5 | 0 | 1 | +140 | bit-6 | |
| 6 | 1 | 1 | +3 | bit-5 | |
| 7 | 2 | 1 | +73 | bit-5 | |
| 8 | 0 | 2 | +143 | bit-5 | |
| 9 | 1 | 2 | +6 | bit-4 | |
| 10 | 2 | 2 | +76 | bit-4 | |
| 11 | 0 | 3 | +146 | bit-4 | |
| 12 | 1 | 3 | +9 | bit-3 | |
| 13 | 2 | 3 | +79 | bit-3 | |
| 14 | 0 | 4 | +149 | bit-3 | |
| 16 | 2 | 4 | +82 | bit-2 | 跳过 Y=15 |
| 17 | 0 | 5 | +152 | bit-2 | |
| 18 | 1 | 5 | +15 | bit-1 | |
| 19 | 2 | 5 | +85 | bit-1 | |
| 21 | 1 | 6 | +18 | bit-0 | 跳过 Y=20，顶边 |

##### N（LE 索引）地址公式

同一个 LAB 中的 16 个 LE，它们的 CRAM 地址按以下规律递减：

```
N=0 → 偏移 0（基准）
N=2 → -2
N=4 → -8
N=6 → -10
N=8 → -16
N=10 → -18
N=12 → -24
N=14 → -26
N=16 → -38（跨越 LAB 中间边界，多减 12）
N=18 → -40
... 以此类推

步长序列：-2, -6, -2, -6, -2, -6, -2, -12, -2, -6, -2, -6, -2, -6, -2

公式：delta(N) = -(half * 38) - (kh // 2) * 8 - (kh % 2) * 2
  其中 k = N/2, half = k//8, kh = k%8
```

##### 完整地址计算示例

**问题**：LE 在 (X=10, Y=10, N=6) 的第 3 对 LUT TT ctrl 字节在 RBF 的哪个位置？

```
1. 查列基地址：COLUMN_BASE[10] = 0x13FDA = 81,882
2. 计算 period_start = 81,882 - 136 = 81,746
3. Y=10: cram_row=8, slot=2, group=2
   slot_base[2] = 70, 偏移 = 70 + 2*3 = 76
4. pair=3 对应 pair 偏移 = 3 * 210 = 630
5. N=6: k=3, half=0, kh=3 → delta = -(1*8 + 1*2) = -10
6. 最终地址 = 81,746 + 76 + 630 + (-10) = 82,442 = 0x1422A
7. bit 位置 = (6 - 2) = 4，即 bit-4
```

#### Phase 2.3：DFF（D 触发器）配置

**挑战**：Quartus Lite 版本**拒绝** `LCFF_Xx_Yy_Nn` 形式的放置约束。这意味着我们无法像 LUT 那样精确控制触发器的位置。

**解决方案**：
1. 使用特定的输出引脚来"吸引"触发器到目标列（Quartus 会自动将 FF 放在靠近输出引脚的 LAB 中）
2. 通过 pair-diff 方法隔离 FF 相关的 bit

**发现**：
- 每个 LE 有 **4 个 FF 配对**（vs LUT 的 8 个），使用相同的 ctrl+data 结构
- FF 配对分布在 LUT TT 区域的**两侧**（一半在下方，一半在上方）
- 添加一个基本 DFF 会改变约 362 个 bit，其中 ~90% 是布线，~10% 是 LE 配置
- FF 模式位（异步复位/同步使能）：82 个共享模式 bit + 功能特定的布线

#### Phase 2.4：算术模式

用行为级描述（`a + b`）编译一个加法器，Quartus 会使用 LE 的算术模式和进位链。

通过与正常模式 LUT 的差分，隔离出 **92 个纯算术/进位链 bit**，分布在 LUT TT 区域两侧（与 FF 类似的分裂模式）。

---

### Phase 3：破解布线矩阵（进行中）

布线矩阵是 FPGA 中连接各个 LE 的"电线网络"。这是逆向工程中最困难的部分。

#### 布线资源类型

```
EP4CE6 的布线资源：

  ┌─────────┐     C4 线       ┌─────────┐
  │  LAB    │ ←───(~4行)───→ │  LAB    │
  │ (X,Y)  │                 │ (X,Y+4) │
  └────┬────┘                 └─────────┘
       │
     R4 线 (~4列)
       │
  ┌────┴────┐
  │  LAB    │
  │ (X+4,Y) │
  └─────────┘

C4  = Column wire, 跨约 4 行 (21,816 条)
R4  = Row wire, 跨约 4 列 (28,186 条)
C16 = Column wire, 跨约 16 行 (1,326 条)
R24 = Row wire, 跨约 24 列 (1,289 条)
LOCAL_INTERCONNECT = LAB 内部输入多路选择器
LE_BUFFER = LE 输出缓冲器
```

#### 方法论

1. **STA 布线提取**：编译后运行 `report_timing -show_routing`，得到每条路径经过的线网名称
   ```
   例如：A → LCCOMB_X10_Y10 → C4_X10_Y10_N0_I0 → LOCAL_INTERCONNECT_X10_Y14 → LCCOMB_X10_Y14 → Q
   ```

2. **控制距离**：通过改变两个 LUT 的距离来强制使用不同类型的布线资源
   - 同列 dy=1：直接连接
   - 同列 dy=2~4：1 条 C4 线
   - 同列 dy=5~8：2 条 C4 线
   - 同列 dy=9+：3 条 C4 线
   - 同行 dx=1~4：R4 线

3. **布线确定性**：设置 `ROUTER_TIMING_OPTIMIZATION_LEVEL MINIMUM` 后，布线完全确定——5 个不同的 fitter seed 产生完全相同的比特流

4. **并行编译**：使用 Python `multiprocessing.Pool`（4 个 worker），有效速度 ~4 秒/目标

#### C4 开关 CRAM 地址模型（已验证：63 条线，0 个错误预测）

```python
# C4_X{x}_Y{y}_N0_I0 的 CRAM 地址
group = (y - 2) // 3
slot = (y - 2) % 3
byte_offset = LAB_CRAM_END(x) + SLOT_BASE[slot] + 3 * group
bit_position = (6 - group) if slot == 2 else (7 - group)

SLOT_BASE = {0: 2405, 1: 2475, 2: 2338}
```

这个模型使用和 LUT TT 完全相同的 slot/group 编码框架（因为它们共享同一套 CRAM 地址空间），只是基地址不同。

#### R4 开关 CRAM 地址模型（18 个 I-index 已映射）

R4 行导线的开关比 C4 更复杂，每个 R4 "I-index" 有独立的基地址 (BASE)：

```python
# R4_X{wx}_Y{wy}_N0_I{idx} 的 CRAM 地址
prev_lab_x = max(x for x in LAB_X if x < wx)  # 线网 X 坐标的前一个 LAB 列
prev_col_start = COLUMN_BASE[prev_lab_x] - 136

group = (wy - 2) // 3
slot = (wy - 2) % 3

# 三种 slot 有不同的偏移公式
if slot == 0:
    byte = prev_col_start + R4_BASE + 66 + 3*group + (1 if group > 0 else 0)
    bp = 7 - group
elif slot == 1:
    byte = prev_col_start + R4_BASE + (-70) + 3*group
    bp = 6 - group                  # 注意：不是 7-group！这个曾经搞错过
else:  # slot == 2
    byte = prev_col_start + R4_BASE + 3*group
    bp = 6 - group
```

**R4_BASE 查找表**（每个 I-index 有两个 pair 的基地址，全部在 PREV 列）：

| I-index | BASE pair1 | BASE pair2 | delta | 验证情况 |
|---------|-----------|-----------|-------|----------|
| 0 | 3423 | 3842 | 419 | 多列验证 |
| 1 | 3431 | 3850 | 419 | 多列验证 |
| 2 | 3431 | 3851 | 420 | prev=X4,X6,X10,X24,X28 |
| 3 | 3474 | 3895 | 421 | 3 个 Y 值，跨列 |
| 4 | 3423 | 3842 | 419 | 同 I=0 |
| 7 | 3414 | 3835 | 421 | 同 I=10 |
| 10 | 3414 | 3835 | 421 | 多列验证 |
| 11 | 3378 | 3585 | 207 | 2 个 Y 值 |
| 12 | 3597 | 3806 | 209 | 2 个 Y 值 |
| 13 | 3577 | 3786 | 209 | 同 I=15 |
| 14 | 3191 | 待定 | ? | pair1 验证，pair2 未确认 |
| 15 | 3577 | 3786 | 209 | prev=X12,X16,X24 |
| 16 | 3629 | 3835 | 206 | 2 个 Y 值 |
| 17 | 2802 | 3223 | 421 | 5 列验证 |
| 18 | 4057 | 4267 | 210 | 2 列验证 |
| 20 | 2791 | 3001 | 210 | 部分列有效 |
| 22 | 2783 | 2993 | 210 | 小样本 |
| 25 | 2762 | 2972 | 210 | 2 列验证 |

**关键发现**：

1. **R4 开关在前一列 (PREV column)**：R4_X22 的 CRAM bit 在 X=21 列中。这和 FPGA 交换矩阵的物理拓扑一致——行线的开关在它经过的每一列中分别控制。

2. **列依赖性**：所有 I-index 在标准宽度列（7,350 字节）上工作良好，但在 M9K/DSP 附近的大列（X=13 的 76,230 字节、X=26 的 68,880 字节）上会失效。这是因为大列内部有子区域，需要更复杂的地址模型。

3. **两种 pair 间距模式**：delta ≈ 420 的（I=0,1,2,4,7,10）和 delta ≈ 210 的（I=18,20,22,25）。前者的两个 pair 跨越两个 210 字节周期，后者在相邻周期。

4. **BASE 共享**：I=0 和 I=4 共享相同的 BASE；I=7 和 I=10 共享相同的 BASE。

5. **R4 线不只在 LAB 列**：31% 的 R4 线出现在非 LAB 的 X 坐标上（如 X=5,9,14,15,20,27,30,32,33），但它们的开关 bit 仍然在最近的 LAB 列中。

#### LOCAL_INTERCONNECT 开关模型（已验证：70% 交叉验证，22 列）

LOCAL_INTERCONNECT 是 LAB 内部的输入多路选择器——决定哪些信号被连接到 LE 的输入端。

```python
# LOCAL_INTERCONNECT_X{lx}_Y{ly}_N{ln}_I{li} 的 CRAM 地址
col_start = COLUMN_BASE[lx] - 136     # 注意：是本列 (SELF)，不是 PREV 列！

group = (ly - 2) // 3
slot = (ly - 2) % 3
byte = col_start + 70 + pair * 210 + SLOT_OFFSET[slot] + 3 * group
bp = (6 - group) if slot == 2 else (7 - group)

SLOT_OFFSET = {0: 67, 1: -70, 2: 0}   # 和 R4 相同的偏移
```

**关键特征**：

1. **在自身列中**：和 R4 不同，LOCAL_INTERCONNECT 的 bit 在本列 CRAM 中。这合理——LAB 输入选择器是 LAB 自身的配置。

2. **多个 pair**：每个 I-index 激活 1~9 个 pair（位于 pair 0~8，即 CRAM 的最低区域），形成 4 种固定的激活模式：

   | 模式 | 激活的 pair | 适用的 I-index |
   |------|------------|---------------|
   | 全部 9 个 | 0,1,2,3,4,5,6,7,8 | I=2,15,16,18,22,33,34,35,36,37 |
   | 跳过 3,7 | 0,1,2,4,5,6,8 | I=0,30,31 |
   | 偶数 pair | 0,2,4,6,8 | I=24,26,28,29,32 |
   | 每块前 2 | 0,1,4,5,8 | I=4,17,27 |

3. **Pair 0 和 4 是万能 pair**：无论 I-index 是什么，这两个 pair 总是被激活。

#### R24 开关 CRAM 地址模型（I=0 已映射）

R24 行导线跨约 24 列。它的开关使用**固定字节偏移**模型——比 R4 更简单：

```python
# R24_X{wx}_Y{wy}_N0_I0 的 CRAM 地址
prev_lab_x = max(x for x in LAB_X if x < wx)
prev_col_start = COLUMN_BASE[prev_lab_x] - 136

group = (wy - 2) // 3
slot = (wy - 2) % 3
bp = (6 - group) if slot == 2 else (7 - group)   # 与 R4/C4 相同的 bp 公式

# 固定字节偏移——不需要 slot/group 的字节调整：
R24_I0_OFFSETS = [3124, 2705]   # 主（pair 14, pos 184），辅（pair 12, pos 185）
byte = prev_col_start + offset  # 不管 Y 是多少，字节地址都一样！
```

**与 R4 的关键区别**：字节地址是**固定的**——不同 Y 值映射到同一个字节，只有 `bp` 随 Y 变化。这意味着同一 group 内的多个 Y 值会产生读取歧义。

- R24 开关在**前一列 (PREV column)**（与 R4 相同）
- 主 pair：rel=3124（pair 14, pos 184）；辅：rel=2705（pair 12, pos 185），delta=419
- 通过 pair-diff 验证了 5-6 个 wx 列，准确率约 66%
- 观测到 7 个不同的 R24 I-index，仅 I=0（占 73% 的 R24 线网）已映射

#### C16 开关分析（尚未映射）

C16 列导线跨约 16 行。初步分析表明其编码与 C4/R4 **根本不同**：

- pair 边界字节（pos=209/0）显示**多 bit 变化**，而非单 bit 开关
- 不同列之间的 XOR 模式不一致——无通用 slot/group 公式
- 使用 C16 的路径噪声大（每条路径含 3-6 条 R4、2-5 条 C4 线），隔离困难
- 可能需要逐线查表，或完全不同的方法论

#### C4 I!=0 开关（无通用公式）

与 C4 I=0 不同，其他 24 个 C4 I-index 在 CRAM 中的位置**没有** 统一的公式。相同的 I-index 在不同的列上映射到不同的 pair 位置，甚至极性也不一样（有些 bit 是 1=打开，有些是 0=打开）。

目前只能通过逐线查表的方式处理。774 条路由路径中观测到了 24 个不同的 C4 I-index。

#### 布线 bit 的 CRAM 分布

```
一个 LAB 列的 CRAM（~7,350 字节）：

  ┌──────────────────────┐  低地址
  │  FF 区域 A           │
  │  (2 对, ~420 字节)    │
  ├──────────────────────┤
  │                      │
  │  LUT TT 区域          │  8 对 × 210 字节 = ~1,680 字节
  │  + 布线开关交织        │  ← 布线 bit 在 LUT TT 对之间！
  │                      │
  ├──────────────────────┤
  │  FF 区域 B           │
  │  (2 对, ~420 字节)    │
  ├──────────────────────┤
  │  C4 开关区域          │
  │  R4 开关区域          │
  │  其他布线开关          │
  └──────────────────────┘  高地址
```

布线开关 bit 和 LUT TT bit 使用相同的 ctrl+data pair 结构，按 210 字节间距交织在一起。bit 位置（0~7）编码的是**物理目标 Y 区域**，而不是布线距离。

---

## 比特流编解码器 (`bitstream.py`)

基于以上发现，我们构建了一个功能完整的编解码器，不仅能读写 LUT 真值表，还能读写布线开关状态。

### 核心类：`RouteCodec`

`RouteCodec` 是编解码器的核心。它接受一个 RBF 文件和一个零基线（zero baseline）文件作为参考：

```python
from bitstream import RouteCodec

# 创建编解码器实例
codec = RouteCodec("design.rbf", "zero_baseline.rbf")
```

**为什么需要两个文件？** 因为 FPGA 的 CRAM bit 有极性问题——有些 bit 是 "1=开启"，有些是 "0=开启"。通过比较空设计和零基线，编解码器知道每个 bit 的默认极性，从而正确解读开/关状态。

### LUT 真值表读写

```bash
# 步骤 1：校准一个位置（需要 16 次 minterm pair-diff，约 2.5 分钟）
python3 runner.py n_sweep 10 10

# 步骤 2：从 RBF 中读取 LUT 真值表
python3 analyze.py read_tt design.rbf zero.rbf 10 10 0
# 输出：mask = 0x8888 (A & B)

# 步骤 3：将 LUT 真值表写入 RBF
python3 analyze.py write_tt zero.rbf 0x6996 output.rbf 10 10 0
# 生成包含 XOR 门 (A ^ B ^ C ^ D) 的 RBF
```

**验证结果**：
- **CRAM 区域完全一致**（与 Quartus 输出逐 bit 相同）
- 仅在文件头/CRC 部分有 14-16 个 bit 差异（Quartus 元数据，不影响配置）
- 已验证的 mask：0x0000, 0x0001, 0x8888, 0x6996, 0xFFFF, 0xAAAA, 0x5555, 0xDEAD 等共 10 种

**端到端硬件验证（2026-04-06）**：

编解码器已在实物硬件（黑金 AX301 开发板, EP4CE6F17C8）上验证：

```
1. Codec write_tt(zero_baseline, mask=0x8888) → e2e_codec_and.rbf
2. 烧写 FPGA：openFPGALoader -c usb-blaster e2e_codec_and.rbf
3. 硬件行为：默认 LED 亮（按键浮空为高），按 KEY2 或 KEY3 → LED 灭
   （正确：A & B，AX301 按键低电平有效）

4. Codec write_tt(zero_baseline, mask=0x6996) → e2e_codec_xor.rbf
5. 烧写 FPGA：openFPGALoader -c usb-blaster e2e_codec_xor.rbf
6. 硬件行为：按单个键 → LED 亮，同时按两个键 → 灭（正确：A ^ B）
```

编解码器生成的 RBF 产生了**完全正确的逻辑行为**——无需经过 Quartus，比特流编解码器端到端工作正常。

注意：AX301 的按键是**低电平有效**（未按=逻辑 1，按下=逻辑 0）。正确的 openFPGALoader 路径为 `$HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader`（系统自带版本无法识别 EP4CE6 的 IDCODE）。

### 布线开关读写（新功能）

编解码器现在也支持读写布线矩阵的开关状态：

```python
from bitstream import RouteCodec

codec = RouteCodec()
design = open("design.rbf","rb").read()
zero   = open("zero_baseline.rbf","rb").read()

# ========== 批量读取所有布线开关 ==========
sw = codec.read_switches(design, zero)
# 返回 {'c4': [...], 'r4': [...], 'r24': [...], 'li': [...]}
# 每条记录：(wire_name, byte_offset, bit_pos, candidates)
# LI 的 wire_name 现在是 base 粒度："LI_X10_Y5_P3B0"
#   P3 = pair 索引，B0 = base offset 70（B1 = base offset 71）

# ========== 把开关写进空白基线 ==========
ops = [
    {'type': 'c4', 'x': 10, 'y': 5, 'i_idx': 0},
    {'type': 'c4', 'x': 13, 'y': 8, 'i_idx': 3},          # 自动走 I≠0 查表
    {'type': 'r4', 'wx': 22, 'y': 8, 'i_idx': 17},
    {'type': 'li', 'lx': 10, 'ly': 5,
     'pair_bases': [(0,0),(0,1),(2,0),(2,1),(4,0),(4,1),(6,0),(6,1),(8,0)]},
]
new_rbf = codec.apply_routing(zero, ops)

# ========== 烧录前的硬件安全检查 ==========
codec.validate_safe_for_hardware(new_rbf, zero)
# 如果某个 LAB 的 LI 激活模式落在「Quartus 从未观察过」的形状之外
# （cell 数错、缺 anchor、paired/alternating 模式破损等），就会 raise

open("output.rbf","wb").write(new_rbf)
```

注意：`li` op 现在必须传 `pair_bases` 显式列表——以前那种「传一个 I-index 自动展开成 9 对」的写法已经移除了。原因是真实 Quartus 在每个 LAB 上最多只会激活 9 个特定的 cell，自动展开会让多条布线通道同时驱动同一个 LE 输入端，那是真硅片上的物理短路风险。

**当前覆盖率**：
- C4 I=0：100%（63 条线全部正确）
- R4：18/37 个 I-index 已映射（~90.5% 线网覆盖率，~77% 直接验证准确率）
- R24 I=0：固定字节模型已映射（~66% 的 pair-diff 准确率），覆盖 73% 的 R24 线网
- LOCAL_INTERCONNECT：base 粒度读写完成，两种编码模式已破解
- C4 I≠0：无通用公式，逐线查表（24 条已映射）
- C16：尚未映射（本质上是多 bit 编码，方法论不同）

---

## 布线编解码器：往返一致性 + 硬件安全防线

基本读写跑通之后，下一个问题是：**我们的编解码器真的能往返吗？** 也就是说，从一份真正由 Quartus 生成的 RBF 里把所有布线开关读出来，再把它们写回一份空白基线，最后再读一次——读到的开关集合会和原始读到的一致吗？

### 往返自洽测试

`route_roundtrip.py` 跑的就是这个实验：

```
真正的 Quartus RBF ──► RouteCodec.read_switches() ──► 一串 switch op
                                                          │
                                                          ▼
              空白零基线 RBF ──► RouteCodec.apply_routing(ops)
                                                          │
                                                          ▼
                              再 read_switches() 一次
                                                          │
                              和原始读到的集合做比对
```

如果编解码器是自洽的，这两次读取的 cell 集合必须**完全一致**：0 条 dropped（写漏的）、0 条 hallucinated（写多的）。注意这不是要求「写出来的 RBF 跟 Quartus 的 RBF 一模一样」——那还得连 LUT TT、IO buffer 一起编码。我们只在测布线这一层。

一条列方向路径（Y10→Y5）和一条行方向路径（X10→X22）的结果：

```
column route Y10→Y5: OK  orig=52 repro=52 common=52
row route X10→X22:    OK  orig=65 repro=65 common=65
```

**0 dropped、0 hallucinated。** 布线编解码器内部完全自洽。

为了让这个跑通，加了两样东西：

1. **`write_c4_inz()`** —— C4 在 I≠0 的时候不走通用 slot/group 公式，而是用固定字节偏移。我们用 baseline-diff 挖出了 24 条 (X, I) → byte 的映射。
2. **`'raw'` switch type** —— R24 / LOCAL_INTERCONNECT 的「按线写」方法，一次会动比单条 read entry 更多的 cell（一根线对应 2+ 个 cell）。在 replay 一份 read 的时候，我们改用 `raw` op，每次只翻一个 (offset, bit)，跟 read 的粒度对齐。

### 硬件安全防线 V2

把编解码器生成的 RBF 烧到真正的 AX301 板子之前，我们想拦下任何可能让 LAB 输入选择器短路的东西。多条布线通道同时驱动同一个 LE 输入端，在真硅片上就是物理冲突。

`RouteCodec.validate_safe_for_hardware(rbf, zero)` 会扫描整个 RBF 的 LOCAL_INTERCONNECT 激活，凡是「Quartus 从未做过」的形状都拒绝放行。

```python
codec = RouteCodec()
codec.validate_safe_for_hardware(my_rbf, zero_rbf)   # 不安全就 raise
```

「什么算安全」这个边界是用经验数据画出来的。我们先把 `read_local_interconnect()` 里那个会掩盖 cell 级结构的 `break` 拔掉，然后重跑了一次 21 个 LAB 的扫描。结果发现：**所有** Quartus 的 LI 激活都落进两种定义清晰的模式之一，**每个 LAB 永远是恰好 9 个 cell**：

- **Paired 模式**（21 个里 13 个，多见于列方向）：`P0` 成对（B0、B1 都点亮）+ 4 个中段 pair 也成对 + `P8` 尾巴（一个 base） = 9 cells
- **Alternating 模式**（21 个里 8 个，多见于行方向）：`P0..P7` 各点一个 base，按 `B1,B0,B1,...,B0` 交错 + `P8` 尾巴 = 9 cells
- **永远存在的锚点**：`P0` 和 `P8` 总是出现；`(P0, B1)` 这一格在所有观察到的 class 里都存在

> 「pair」和「base」是什么？LOCAL_INTERCONNECT 的 cell 落在每个 LAB 列里一个以 210 字节为周期的区域。每个周期里有两个字节——offset 70 和 71（也就是 base 70 / base 71，简称 `B0`/`B1`）——是 LI 字节。pair 索引 `P0..P8` 表示我们在列里的第几个 210 字节周期。

V2 分类器 `_classify_li_lab(pair_map)` 会把任意一个 LAB 标记成 `paired`、`alternating` 或 `invalid`（带原因）。守卫会拒绝放行：

- 任何 LAB 的活跃 cell > 9
- 缺 `P0` 或 `P8` 锚点；`P8` 同时点亮两个 base
- Paired 模式但中段 pair 只点了单个 base（破损的 paired）
- Alternating 模式但某个 pair 的 base 错了，或者有任何中段 pair 同时点了两个 base

这套规则在 6 种实际观察到的 Quartus class 上全部通过，在 4 种人造违规上全部拒绝。**之前的 V1 守卫（「每个 LAB 最多 5 对」）其实是错的**：21 个合法 Quartus 配置里有 13 个会被它误杀。

### 这件事顺带破解了「9-pair vs 5-pair 之谜」

之前有好几周，同一个布线 key 在不同 LAB 上读出来是看上去完全不同的两种位模式——有时 5 个 pair 位置共 10 个字节翻转，有时 9 个 pair 位置共 9 个字节翻转。我们一直以为这是两种结构上不同的编码。

其实不是。它们是**同一个 9-cell envelope**用两种不同方式数出来的：
- 「5 pairs × 2 字节 = 10 翻转」是只数了成对的 pair，漏掉了 P8 那个单字节尾巴（实际是 4 中段成对 + P0 成对 + P8 单 = 9 cells）
- 「9 pairs × 1 字节 = 9 翻转」其实数 cell 数一直都对

旧版 reader 在第一次命中后就 `break` 掉了，正好把 paired 和 alternating 之间的差异盖掉了。当我们改成「每 `(pair, base)` 对一个 cell 就发一条 read entry」之后，结构立刻变得肉眼可见。

### 模式选择规则（还没完全破解）

我们拿这 21 个已分类的 LAB 去挖：到底什么因素决定 Quartus 选 paired 还是 alternating？

| 特征 | 是否能预测？ |
|------|-------------|
| 列方向（dy != 0）| ✅ 7 个列方向移动全部 → paired |
| 行方向（dx != 0）| ⚠ 混合：8 alternating + 6 paired |
| 是否邻近非 LAB 列（X=5,9,14,15,20,27,30）| ❌ 无相关性 |
| dst_x 奇偶 | ❌ 无相关性 |
| LAB-list 索引距离 | 弱相关，存在反例 |

所以列方向是确定性的，但行方向的分裂用单一特征还推不出来。最可能漏掉的变量是「进 LI 之前最后一段 R4/C4 的 I-index」——这个值决定走哪一层 LI 输入选择器。要破解它得有更丰富的多 LE 设计语料库。

---

## 快速上手

### 环境准备

```bash
# 1. 安装 Quartus Prime 21.1 Lite
# 从 Intel 官网下载，安装到 ~/intelFPGA_lite/21.1/

# 2. 配置 PATH
export PATH=$PATH:$HOME/intelFPGA_lite/21.1/quartus/bin

# 3. 进入项目目录
cd fuzz
```

### 基本操作

```bash
# 生成基线 RBF
python3 runner.py baseline

# 对 (X=10, Y=10, N=0) 做 LUT pair-diff
python3 runner.py --node lut_inst lut_single 10 10 0

# 查看数据库摘要
python3 analyze.py summary

# 查看某个 LE 的真值表映射
python3 analyze.py lut_table 10 10 0

# 导出完整数据库为 JSON
python3 analyze.py export
```

### 高级操作

```bash
# 扫描一个位置的所有 16 个 minterm（校准编解码器）
python3 runner.py n_sweep 10 10

# 扫描所有 22 列的 pair-diff
python3 runner.py pair_diff_grid

# 并行布线 fuzzing（4 个 worker）
python3 runner.py route_map_parallel 10 5 col

# 批量布线 fuzzing（多个源位置，多方向）
python3 runner.py route_map_batch --sources 4,10 29,10 10,17 --direction col --jobs 4

# 从 RBF 读取真值表
python3 analyze.py read_tt design.rbf zero.rbf 10 10 0

# 向 RBF 写入真值表
python3 analyze.py write_tt zero.rbf 0x8888 output.rbf 10 10 0
```

---

## 已知陷阱和注意事项

1. **左边缘列（X=3,4,6,7）** 的 CRAM 地址在 0x10000 以下，与其他列的地址范围不同
2. **Quartus fit 报告包含非 UTF-8 字节**——读取时要用 `errors="replace"` 参数
3. **不要在共享的 `work/` 目录中并行运行多个 fuzzing campaign**——会互相覆盖文件
4. **`sof2rbf.py` 产生无效比特流**——必须用 `quartus_cpf -c -o bitstream_compression=off`
5. **某些 LAB 位置无效**：X∈{3,4,6,7,8}, Y∈{12,13,14,16} 的组合会被 Quartus 拒绝（这些位置可能被 M9K 或其他硬核占用）
6. **磁盘空间**：Phase 3 的 `work/` 目录会急剧膨胀，每次编译后应清理（`compile.py` 提供了 `clean_work_dir()` 函数）

---

## 当前进度和下一步

### 已完成 ✓

- [x] Phase 1：自动化 fuzzing 管线搭建
- [x] Phase 2.1：LUT 真值表 XOR 线性编码模型（16 bit × 376 位置 = 100%）
- [x] Phase 2.2：完整 CRAM 地址模型（X/Y/N 三维公式，376/376 验证）
- [x] Phase 2.3：DFF 配置位映射
- [x] Phase 2.4：算术模式位映射
- [x] Phase 2.5：LUT TT 编解码器（读写验证通过，10 种 mask 验证 bit-identical）
- [x] Phase 3.1：C4 I=0 开关地址模型（63 条线，0 错误预测，22 列通用公式）
- [x] Phase 3.2：R4 开关地址模型框架（slot/group 公式 + PREV 列定位）
- [x] Phase 3.3：R4 slot=1 偏移量修正（bp = 6-group，0%→78% 修复）
- [x] Phase 3.4：R4 I-index 映射 — 13/37 个已映射（I=0,1,2,4,7,10,14,15,17,18,20,22,25）
- [x] Phase 3.5：LOCAL_INTERCONNECT 开关建模（70% 交叉验证，22 列，4 种 pair 激活模式）
- [x] Phase 3.6：布线编解码器（RouteCodec 读写方法：C4/R4/LOCAL_INTERCONNECT）
- [x] Phase 3.7：R24 I=0 固定字节模型（~66% pair-diff 准确率，覆盖 73% 的 R24 线网）
- [x] Phase 3.8：C4 I≠0 逐 (X,I) 固定字节查表（24 条映射，11 个 I-index）
- [x] Phase 3.9：RouteCodec 往返自洽（列、行路径均 0 dropped、0 hallucinated）
- [x] Phase 3.10：LOCAL_INTERCONNECT base 粒度读 API（每 (pair, base) cell 单独发一条）
- [x] Phase 3.11：LI 编码模式破解 —— paired vs alternating，统一 9-cell envelope
- [x] Phase 3.12：硬件安全防线 V2（带特征识别的 `validate_safe_for_hardware`）
- [x] Phase 3.13：AX301 端到端硬件验证（编解码器 → 烧录 → 逻辑行为正确）

### 进行中

- [ ] Phase 3.14：映射剩余 ~19 个 R4 I-index（I=3,6,8,9,11,12,13,16,19,21,23,26,27,28 等）
- [ ] Phase 3.15：M9K/DSP 边界列修复（X=13/26 等大列需要子区域地址模型）
- [ ] Phase 3.16：C16 长距离线建模（完全未映射）
- [ ] Phase 3.17：LI 模式选择规则挖掘 —— Quartus 凭什么选 paired vs alternating？（需要更丰富的多 LE 路径语料库）

### 未来工作

- [ ] Phase 4：完善布线编解码器覆盖率（目标：所有线类型 >90%）
- [ ] Phase 5：FASM 格式适配（与 Yosys/NextPNR 对接）
- [ ] Phase 6：NextPNR EP4CE6 后端开发

### 整体进度估算

| 领域 | 进度 | 说明 |
|------|------|------|
| 逻辑配置（LUT/FF/算术） | **~95%** | 全部 LE 位置的 LUT TT 已解码，FF 和算术模式已映射 |
| CRAM 地址映射 | **100%** | 22 列 × 18 行 × 16 LE = 376/376 位置全部验证 |
| C4 布线开关 | **~55%** | I=0 100% 公式；I≠0 24 条逐 (X,I) 固定字节查表 |
| R4 布线开关 | **~50%** | 18/37 个 I-index 已映射，~90.5% 线网覆盖，~77% 直接准确率 |
| LOCAL_INTERCONNECT | **~85%** | base 粒度读写；两种编码模式破解；V2 硬件安全防线 |
| R24 长距离线 | **~30%** | I=0 固定字节模型，覆盖 73% R24 线网 |
| C16 长距离线 | **0%** | 尚未开始 |
| 比特流编解码器 | **~70%** | LUT TT + 布线读写完成；往返自洽；硬件安全防线 V2 |

---

## 参考资料

- [Cyclone IV Device Handbook](https://www.intel.com/content/www/us/en/docs/programmable/683853/current/cyclone-iv-device-handbook.html)
- [Project IceStorm](http://www.clifford.at/icestorm/) — iCE40 逆向工程，方法论范本
- [Project Mistral](https://github.com/Ravenslofty/mistral) — Cyclone V 逆向工程，同家族参考
- [Quartus Prime Lite](https://www.intel.com/content/www/us/en/products/details/fpga/development-tools/quartus-prime/resource.html) — 免费 FPGA 开发工具

---

## 许可证

本项目仅用于教育和研究目的。逆向工程的结果用于构建开源 FPGA 工具链。
