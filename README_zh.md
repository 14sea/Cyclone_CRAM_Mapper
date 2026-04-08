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
├── fuzz/                   ← Fuzzing 管线（Python 源代码，96 个模块）
│   ├── config.py           ← EP4CE6 常量、坐标、引脚定义
│   ├── verilog_gen.py      ← Verilog 代码生成器
│   ├── qsf_gen.py          ← Quartus 工程配置文件生成器
│   ├── compile.py          ← Quartus 无头编译驱动
│   ├── rbf_diff.py         ← Bit 级二进制差分引擎
│   ├── database.py         ← SQLite 数据库接口
│   ├── runner.py           ← Fuzzing 实验编排器（主入口）
│   ├── analyze.py          ← 结果分析和可视化
│   ├── bitstream.py        ← Bitstream 编解码器（LutCodec + RouteCodec + CRC 修补）
│   ├── route_synth.py      ← 绿区路由综合引擎
│   ├── fasm2rbf.py / rbf2fasm.py ← Phase 4 FASM 写入器 + 反向工具
│   └── route_signatures.py / route_decompose.py ← 签名后端 + 集合覆盖分解
├── jailbreak/              ← CE10 fitter 探针（X=32/33、Y=15 坏点扫描）
├── results/
│   ├── rbf/                ← 收集的 .rbf 文件（~2,500 个，各 368 KB）
│   ├── fingerprint_*.json  ← 15 个绿区 island 语料
│   ├── route_cells.json    ← 1050 条路由 signature 后端
│   ├── source_overhead.json ← per-source 相对 baseline 的开销
│   ├── r4_iindex_table.json ← 942 条 R4 I-index 提示表
│   ├── ep4ce6_bitdb.sqlite ← Bit 映射数据库
│   └── FINDINGS.md         ← 详细发现报告
└── work/                   ← Quartus 临时编译目录（可清理）
```

### 源代码统计（核心模块）

| 文件 | 行数 | 功能 |
|------|------|------|
| `config.py` | 184 | 芯片常量、CRAM 地址公式、引脚定义 |
| `verilog_gen.py` | 363 | Verilog 生成（LUT/FF/LI/route/越狱模板） |
| `qsf_gen.py` | 81 | QSF 项目配置生成 |
| `compile.py` | 270 | Quartus 编译流程驱动 + STA 路由提取 |
| `rbf_diff.py` | 111 | 二进制比较引擎 |
| `database.py` | 193 | SQLite 数据库操作 |
| `runner.py` | 1,305 | 实验编排器（最大的文件） |
| `analyze.py` | 570 | 分析、可视化和编解码命令 |
| `bitstream.py` | 1,264 | **LutCodec + RouteCodec + CRC 修补** |
| `route_synth.py` | 398 | 绿区路由综合 |
| `fasm2rbf.py` | 239 | Phase 4 FASM → RBF |
| `rbf2fasm.py` | 175 | Phase 4 RBF → FASM |
| **核心合计** | **~5,150** | （另有 84 个挖矿/分析/测试模块） |

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
- **1,961** 次实验
- **708,319** 条 bit 映射记录
- **980** 条布线路径（含 STA 提取的完整线网路径）
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

#### R4 开关 CRAM 地址模型（37 个 I-index 中已映射 25 个）

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

目前只能通过逐线查表的方式处理。980 条路由路径中观测到了 24 个不同的 C4 I-index。

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
- R4：25/37 个 I-index 已映射（剩余 12 个卡在路由语料不足）
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

在这项工作的相当一段时间里，同一个布线 key 在不同 LAB 上读出来是看上去完全不同的两种位模式——有时 5 个 pair 位置共 10 个字节翻转，有时 9 个 pair 位置共 9 个字节翻转。我们一直以为这是两种结构上不同的编码。

其实不是。它们是**同一个 9-cell envelope**用两种不同方式数出来的：
- 「5 pairs × 2 字节 = 10 翻转」是只数了成对的 pair，漏掉了 P8 那个单字节尾巴（实际是 4 中段成对 + P0 成对 + P8 单 = 9 cells）
- 「9 pairs × 1 字节 = 9 翻转」其实数 cell 数一直都对

旧版 reader 在第一次命中后就 `break` 掉了，正好把 paired 和 alternating 之间的差异盖掉了。当我们改成「每 `(pair, base)` 对一个 cell 就发一条 read entry」之后，结构立刻变得肉眼可见。

---

## 路由综合：跳岛策略（Island Hopping）

读侧编解码器扎实之后，下一个问题是反向：**给定 (src, dst)，能不能合成出和 Quartus 逐 cell 一致的布线比特流？** 我们试过纯公式驱动的合成器，发现根本走不通。原因是：

> **Cyclone IV 的 CRAM 是「交错」的，而不是与芯片拓扑同构。** 每个 LE 的布线 CRAM cell 散落在远离源 LAB 列的不重叠物理区域里，**跨源指纹交集为空** —— 不存在一个跨源 LAB 通用的「源进入码」。

所以 `route_synth`（在 `fuzz/route_synth.py` 里）换了个思路：**逐源语料挖掘 + bit-perfect 快照重放**。每个「绿区岛」是一个 `(sx, sy)` 源 LAB，我们对它有：

1. 一小批 `lits_pair_X{sx}Y{sy}_to_*` 的 Quartus 编译语料
2. 一份**源指纹**（这个源所有路由 100% 都会出现的 cell）
3. 一份**逐路差量**（每个 dst 在指纹之外的剩余 cell，原始 `(offset, bit)` 列表）

对语料里已有的 dst，`synth_route()` 直接以 raw cell 的形式发出 `指纹 ∪ delta[dst]`，得到的比特流在布线区与 Quartus 字节级一致。对语料外的 dst，则回落到公式化的 plan（C4/R4/R24 跳 + LI envelope），并由 `validate_safe_for_hardware()` 把关，防止把 LAB 推到未知 LI 激活模式。

### 三座岛战报

| 岛 | 位置 | 路由数 | 指纹 bit | bit-perfect | 往返 | 安全（synth/quartus） | 黄区探针 |
|----|------|--------|----------|-------------|------|----------------------|----------|
| α | (10, 10) — 内陆 | 31 | 6 | 31/31 | 31/31 | 31/31 / 31/31 | 3/3 |
| β | (10, 14) — M9K 边界（Y15 鬼行） | 11 | 11 | 11/11 | 11/11 | 11/11 / 11/11 | 3/3 |
| γ | (4, 4) — 角落 | 16 | **1** | 16/16 | 16/16 | 16/16 / 16/16 | 3/3 |
| **合计** | | **58** | | **58/58** | **58/58** | **58/58** | **9/9** |

几个反直觉的结论：

- (4, 4) **角落**反而拥有三座岛中**最小**的指纹（只有 1 个 bit，`R4_X11_Y5_N0_I3`）。原本以为角落需要更多「edge bit」，结果完全相反 —— 角落的逐路差量几乎吸收了所有东西。
- 一个早期的「GND tie 假说」 —— 即 (10, 14) 那 11 个指纹 bit 是未路由 lut2 输入被绑到 GND 的副作用 —— 被一组受控的多输入编译实验（`purify_fingerprint.py`）**证伪**：把 lut2 的 4 个输入全部接上真实信号后，指纹不仅没缩小，反而略微变大。
- 我们从语料里挖出了好几条**全局恒亮**的结构，对任何已知源的跨 LAB 路由都会无条件发出：源侧 R4 启动驱动器（`R4_X{sx+1}_Y{sy}` 的 I=1 + I=2）、源列 R24 broadcast hold（5 个 raw bit）、LI 源驱动器 MUX（`P8B0+P8B1`，仅在相邻 ±1 横向跳时跳过）。三者都在对应的 `lits_pair_*` 语料里以 100% 命中率挖出。

### 测试

`fuzz/test_green_zone_harden.py` 自动发现 `results/fingerprint_{sx}_{sy}.json` 所有快照，对每座岛跑 5 项检查（vs Quartus bit-perfect、编解码器往返、safe-synth、safe-quartus、指纹漂移），再加 3 个「黄区」探针（语料外 dst，至少要通过 `validate_safe_for_hardware`）。当前三座岛全部 0 漂移通过。

---

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

## 调试日记：我们是怎么把硬件回环闭合的

这一节是写给新人的故事 —— 它讲述了我们如何把编解码器从「对 Quartus
bit-perfect」推进到「真实矽片接受我们手工生成的比特流，按键能控制 LED」。
这里的每一步都是真实踩过的坑，绝大多数在踩之前都不显然。

### 起点：codec 输出看起来完美，但 FPGA 拒收

完成 Phase 3 后，我们的 `RouteCodec` 已经可以从任意 Quartus 生成的 `.rbf`
读出布线开关，再用 `apply_routing()` 重放到空白 baseline，然后无损地再读一遍。
把 codec 输出和原始 Quartus RBF 做 diff，**0 个 CRAM 字节差异** —— 每一个
配置位都一模一样。该上真硬件了。

我们接上一块黑金 AX301（EP4CE6F17C8 + USB-Blaster JTAG）然后跑：

```bash
openFPGALoader -c usb-blaster results/rbf/lits_synth_X10Y10_to_X12Y10N0_datab.rbf
```

烧录看起来成功了。但板子上的 LED 跑起了我们从来没编译过的「跑马灯」demo
—— FPGA 在跑 **EPCS 配置 Flash 里的厂商示例**，根本没在跑我们的比特流。
对照实验：直接烧一个已知正确的 Quartus 编译的 RBF —— 那个跑得对。我们甚至
故意把一个正确的 RBF **翻一个 bit**（`lits_pair_BITFLIP_test.rbf`），结果
FPGA 也拒绝了，照样跳回 EPCS demo。

**结论**：Cyclone IV 配置状态机会在加载时校验比特流。一字节不对它就静默地
回退到 Flash boot。RBF 里一定藏着 CRC 或 checksum，而我们「CRAM bit-perfect」
的把戏漏掉了它。

### 发现并逆向 CRC

我们手上没有 .rbf 格式的官方文档，所以只能纯靠观察现成的比特流来推算 CRC
算法。具体步骤如下。

**第一步 —— CRC 是有状态的吗？** CRC 可以是整个比特流上一个滚动值，也可以
是每帧固定大小的独立值。我们扫描语料库，找出 **数据字节完全相同的帧对**：
如果它们的 CRC 字节也匹配，那算法就是无状态的（每帧独立）。我们找到 **1186
对完全相同数据的帧**，每一对的尾随 CRC 字节都吻合。✓ 无状态。CRC 是逐帧
独立计算的。

**第二步 —— 找帧大小。** RBF 总长 368,011 字节。减掉 32 字节 0xFF 前导和
59 字节 0xFF 尾导，剩 367,920 = **1752 × 210**。Bingo：1752 帧，每帧 210
字节。每帧大概率是 208 字节数据 + 2 字节 CRC（小端）。

**第三步 —— ΔCRC 线性搜索。** 这是整个破解的关键技巧。我们不去对单帧的
绝对 CRC 暴力 65,536 个多项式（直接做的话零命中 —— 自由度太多），而是用
**线性约束**：

- 构造两段合成的 208 字节负载，**只在一个字节上不同**（例如：byte 100 = 0x10
  vs. byte 100 = byte 101 = 0x10）。
- 对每个候选 (多项式 × bit-direction) 组合，这两段的 CRC 差完全由多项式决定
  —— 不需要知道初值。
- 要求同一个多项式同时满足两个 ΔCRC 约束（双约束）。这一刀就把
  65,536 × 4 个候选砍到几乎为零。

只剩两个多项式幸存：标准的 **0x8005**，加上一个低权重碰撞 0x0006。0x8005
反射后是 0xA001（右移形式）。这就是 CRC-16-IBM。

**第四步 —— 暴力破解 init。** 光有多项式还定不了 CRC，还有个寄存器初值。
确定多项式后，我们挑出语料库里 1316 帧全零数据的帧，要求
`crc16(zeros, poly=0x8005, init=?) == observed (0x7d9a)`。只有一个 init
满足：**0xFE54**。

**第五步 —— 端到端验证。** 公式钉死后：

```python
def crc16_rbf(data208: bytes) -> int:
    crc = 0xFE54
    for b in data208:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return crc
```

…我们对一个已知正确的 Quartus RBF 跑了 **全部 1752 帧**。结果：**1727 帧
匹配，25 帧失败**。这 25 个失败是连续的一段 —— **frames 0..24**。那是
比特流的 header（同步字、配置寄存器、设备级开关）。**header 不被 CRC
保护**；只有 frames 25..1751（CRAM 帧）有强制 CRC。把 header 从 patcher
里排除掉，每一个 CRAM 帧的 CRC 都精确吻合了。

完整规格在 `bitstream.crc16_rbf_frame()` 和 `patch_rbf_crc()`。

### Codec / CRC 字节重叠（以及怎么修）

把 CRC patcher 接进 `synth_route()` 之后再跑绿区回归测试，瞬间炸了：
**58/58 路由 bit-perfect → 0/N**。Patcher 把 codec 玩坏了。

为什么？CRC 字节位于每个 210 字节 **帧** 的偏移 `+208` 和 `+209`。但 codec
扫描 LAB 列时用的 **210 字节周期不是帧对齐的**（列基址和帧起点不一致）。
所以 codec 的「slot 1」或「slot 2」读偶尔会正好落在 patcher 刚刚改写的字节
上 —— 与 zero baseline 做 diff 时就把 CRC 差当成「布线变化」吃进去了。

修复方法在概念上很简单：在算任何布线 diff 之前，**把 CRC 字节位置 mask
掉**，让它们看起来跟 baseline 一样。这就是 `bitstream.py` 里的
`mask_rbf_crc_bytes()`，在 `read_switches()` 顶部自动调用。这之后我们就敢
把 `synth_route()` 的 `patch_crc=True` **设为默认开启**，绿区回归也回到了
58/58。

### 第一次硬件回环闭合

CRC patcher 整合好之后，我们再次烧入用 codec 自己合成的布线 RBF。这次
JTAG 加载完成 *并且 LED 安静下来* —— EPCS demo 没有抢回控制权。FPGA
正在跑我们的比特流。**回环闭合。**

接着我们试 `LutCodec.write_tt(minterm_0_baseline, mask=0xFFFF)` —— 把 LUT
真值表覆盖成常数 1。烧录、检查：LED 亮。再烧 Quartus 编译的 `minterm_0`
（mask=0x0000，常数 0）作对照：LED 灭。**两个相反的状态证明
`LutCodec.write_tt` 成功打到了矽片上。**

意外发现：当我们对 LutCodec 输出跑 `patch_rbf_crc()` 时，它改了 **0 个
字节**。CRC 已经是对的。为什么？因为 LutCodec 的 bit pattern 是从 Quartus
pair-diff 训练出来的，pair-diff 里本身就包含了 CRC 字节的变化 —— 所以
写一个新的 TT 隐式地产出 CRC 正确的比特流。RouteCodec 没有这个性质，因为
它用的是逆向出来的公式而不是 pair-diff 重放。

### 用硬件探针定位 AX301 引脚

为了做一个真正的功能 demo，我们需要 `LED0 = f(K1, K2, K3, K4)` 行为正确。
但 `config.py` 里写着 `D = PIN_E15  # RESET` —— 标成了 reset 引脚而不是
按键。早些时候的硬件实验（`LED = A & B & C & D`）发现 LED 怎么按都不动，
暗示引脚标签可能错了。我们不信任 AX301 的电路图 PDF（也不容易拿到），
所以干脆做一台 **矽片引脚扫描仪**。

技术：写一行 Verilog `assign LED = K`，编译 4 次，每次把 `K` 绑到不同的
候选引脚（`PIN_E16`、`PIN_M16`、`PIN_M15`、`PIN_E15`），LED 全都接
`LED0 = PIN_G15`。逐个烧录。每次烧完按下全部 4 个实体按键。**让 LED 熄灭
的那个键就是这个引脚。**（按键是 active-low，按下把输入拉到 GND，
`assign LED = K` 把这个 0 直接传到 LED0。）

四次烧录，四个答案（`pin_probe.py`）：

| 引脚    | 实体按键 |
|---------|----------|
| PIN_E15 | **KEY1**（之前误标为 "RESET"） |
| PIN_E16 | KEY2 |
| PIN_M16 | KEY3 |
| PIN_M15 | KEY4 |
| PIN_G15 | LED0（active-high）|

`D` 输入一直接的就是 KEY1，根本不是 reset 引脚。带着这张矽片亲自验证过的
表，我们更新了 `config.py` 并把它记进了 memory。

### 最后的功能 demo 与 XOR-delta 暗坑

目标：**「同时按 K1+K2 或同时按 K3+K4 → LED 亮，否则灭。」** 这个函数用满
4 个输入，又有令人满意的物理交互。

FUZZ_PINS 是 A=K2、B=K3、C=K4、D=K1，按键 active-low，所以函数是
`Q = (¬D ∧ ¬A) ∨ (¬B ∧ ¬C)`。逐位算真值表 mask 得到 `0x0357`
（bits {0,1,2,4,6,8,9} 置位）。

我们用 `LutCodec.write_tt()` 把这个 mask 写到 `minterm_0_X10_Y10_N0.rbf`
baseline 上，patch CRC，烧录，开始按键。**6 个测试用例里 5 个对了。**
有一个错了：4 个键全按时 LED 灭，但函数说应该亮。

把 codec 输出 round-trip 读回来 —— 是 `0x0357`，跟我们写的一字不差。那
为啥硬件觉得 bit 0 是 0？

Bug 是这个：**`LutCodec.write_tt(base, mask)` 不是绝对写，是对 `base` 的
XOR-delta**。Codec 算的是「相对真正的 0x0000 baseline，这个 mask 应该翻
哪些 CRAM cell」，然后把这些 cell XOR 到你传进去的 `base` 上。所以硬件上
的真值表是 `base_tt XOR mask`，而不是 `mask`。

我们的 `base` 是 `minterm_0_X10_Y10_N0.rbf`。看一下 `minterm_0` 实际是什么：
它是 `Q = ~A & ~B & ~C & ~D` 这个设计，只在所有输入都为 0 的时候输出 1。
所以 `minterm_0` 的 LUT TT 是 `0x0001` —— bit 0 已经是 1 了。

写完之后硬件上的真值表是 `0x0001 XOR 0x0357 = 0x0356`。`0x0356` 的 bit 0
是 **0**。这正好对应「4 键全按」那个用例 —— 输入 (D,C,B,A) = (0,0,0,0)
→ TT[0] → 0 → LED 灭。Bug 跟症状完全对得上。

`read_tt` 是对称的（也返回相对 `base` 的 delta），所以 round-trip 读根本
抓不到这个 bug —— 写和读用的是同一套 XOR 约定。

修复就一行：写 `mask ^ base_tt` 而不是 `mask`。

```python
TARGET = 0x0357
MASK = TARGET ^ 0x0001   # 补偿 minterm_0 的 TT[0]=1
```

重烧，4 个键全按 → **LED 亮**。只按 K1+K2：LED 亮。K3+K4：LED 亮。其他
任何组合（单键、K1+K3、K2+K4 等）：LED 灭。**完整真值表通过物理按键验证。**

### 附赠发现：EP4CE6 和 EP4CE10 是 **同一颗物理矽片**

Phase 3 之后一个自然的问题是：「能不能用 EP4CE10 来交叉验证我们的 CE6
逆向结果？毕竟它们共用 F17 封装，而且坊间一直传它们是同一颗矽片。」与
其猜，我们直接做了一个最干净的实验（`fuzz/cross_device_diff.py`）：

- 用一行 Verilog（`assign LED = K`）+ **完全相同** 的引脚分配，在两个
  device target 下编译：
  - `DEVICE = EP4CE6F17C8`
  - `DEVICE = EP4CE10F17C8`
- Byte-diff 两个 RBF。

**结果**：

| | EP4CE6F17C8 | EP4CE10F17C8 |
|---|---|---|
| 文件大小 | 368,011 bytes | 368,011 bytes |
| SHA1 | `b47e804074b05d3d…` | `b47e804074b05d3d…` |
| 字节差异 | **0** | |

不是「几乎相同」—— 是**逐字节完全相同**，连 header 里 device ID 字段都
一样。Altera 甚至没有在 CRAM 里加一个 bit 来 gate 被禁用的区域。
「6,272 LE vs 10,320 LE」的差异**完全是 Quartus 软件层面的限制**；矽片
本身是同样的金属层、同样的 fuse、同样的 device ID。

**这件事的战略价值**。重新跑 CE10 的 Phase 1/2 完全是冗余 —— SQLite 会
是 100% 的重复数据。但这个结论解锁了一个更强大的技巧：**CE10 是 CE6 的
「越狱版 Quartus」**。每当 Quartus 在 CE6 模式下拒绝把逻辑放到某个被
软件视为禁区的位置（M9K 边界、X=13 / X=26 这种巨型列、为更大 LE 池保留
的区域），我们可以把项目 `DEVICE` 切到 EP4CE10F17C8，强制放置，编译，
再把出来的 RBF 直接喂给同一个 RouteCodec / LutCodec / CRC patcher —— 因为
底层 CRAM 没变。CE6 软件不肯生成的那些 bit 就在同样的位置，只是需要换一个
软件 profile 把它们诱骗出来。

### 完整越狱：CE6 的版图是一场集体造假

2026-04-07。拿到「同一颗 die」的结论之后，我们决定真正去**摸**一下
Altera 藏起来的那块矽。方法蠢得一目了然：写一个 trivial 的 Verilog，
把一颗 `cycloneive_lcell_comb` 锁在具体的 `LCCOMB_Xa_Yb_N0`，项目挂
`DEVICE = EP4CE10F17C8`，跑 `quartus_fit`，读 fitter 的裁决。
`"Fitter was successful"` = 这个座标物理上存在。`"illegal location
assignment"` = Quartus 还在耍赖。扫一遍 (X,Y) 网格就得到一张
die 的 yes/no 真实地图。

结果令人发指：

| CE6 宣称 (`config.py` / `CLAUDE.md`) | CE10 探针的真相 |
|---|---|
| `LAB_X = [3,4,6,7,8,10,11,12,13,16,17,18,19,21,22,23,24,25,26,28,29,31]`（22 列） | **28 列** —— 新增 X=5, 9, 14, 30, 32, 33 |
| `NON_LAB_X = {5, 9, 14, 15, 20, 27, 30}`（7 列 M9K/DSP/PLL） | **只有 {15, 20, 27}** —— 另外四列是真 LAB |
| `LAB_Y = [2..14, 16..21]`（19 行，跳过 Y=15） | **20 行** —— Y=15 在 X ∈ {10,14,16,21,25,30,31,32,33,...} 是真 LAB 行 |
| 总 LAB 数：392 | **~520+** |
| 总 LE 数：6,272 | **10,320**（刚好等于 CE10 datasheet） |

换句话说，CE6 标成「非 LAB」的 7 列里有 4 列是谎言；一整行 (Y=15)
是谎言；最右边两列 (X=32,33) 是谎言。fitter 硬编了一份白名单，把 ~40%
的 die 删掉，然后把这颗芯片贴上小号型号的标签卖出去。

**用 XOR 链证明 LE 真的活着**。声称某个座标存在，和声称那颗 LE 真的
**能用**，是两回事 —— rebin 很多时候就是因为某几列 yield 失败。为了
分开这两件事，我们写了一个单 bitstream 坏点扫描器
(`jailbreak/scanC_gen.py`)：

```
chain[0] = K1 ^ K2
for 每一颗禁区 LE i：
    (* keep, preserve *)
    chain[i+1] = cycloneive_lcell_comb(dataa=chain[i], lut_mask=0xAAAA)  // 恒等传递
LED = chain[N]
```

每一颗 LUT 都把自己的 `dataa` 原样传过去。数学上化简成
`LED = K1 ^ K2`，**当且仅当链中每一颗 LE 都正常工作**。任何一个
stuck-at、一条断掉的布线、或者一个 LUT mask 写错，都会在四种按键组合里
至少一种上翻转输出奇偶性，LED 会立刻出卖坏点。

三个阶段，AX301 上烧三次：

| 阶段 | 范围 | 链中 LE 数 | 硬件结果 |
|---|---|---|---|
| A | X ∈ {32,33}, Y ∈ [2..21], N=0 | 40 | ✅ 四组真值表全中 |
| B | X ∈ {32,33}, Y ∈ [2..21], N ∈ {0,2,…,30} | 640 | ✅ |
| C | X ∈ {5,9,14,30,32,33}（禁区 6 列）+ Y=15 整行, 全 N | **1,840** | ✅ |

2,480 颗独立的 CE6-隐藏 LE，每颗过四种按键组合，无一例外表现得像完美
的矽片。**手上这块 AX301 板不是 rebin 次品，是一颗 Altera 贴着 CE6
标卖的、功能完整的 CE10 die。**

对项目的意义：现有的 CRAM / C4 / R4 / LI 模型**不需要推翻**，只要扩容。
六条新 LAB 列各自加一个 `COLUMN_BASE`，`LAB_Y` 加上 Y=15，其他全部
沿用 —— 配对间距、slot/group 编码、LI mode 分类、CRC 帧布局，全都
原样兼容，因为底下的矽片就是同一片。可布线 fabric 增加 ~32%，可寻址
CRAM 增加 0 字节。

我们**故意暂时不**在 `bitstream.py` 里自动打开扩展版图。打开的条件是：
(1) 用 baseline-diff 挖出每条新列的 CRAM base，(2) 至少在 X ∈ {32,33}
其中一个作为新 source 跑通 green-zone 回归，确认 RouteCodec 的不变式
在 fabric 边缘还成立。两件都是机械性的后续工作，没有新物理。

跨 die 对比（EP4CE15 / EP4CE22）是另一个完全不同的问题 —— 它们大概率
是「Die B」，列数不同，需要重新推导 column base。我们刻意暂时不追这条
路线：把 CE6 的布线覆盖率做完，比追一个更广的器件家族更快通向可用的
开源工具链。

### 我们学到了什么

1. **相信矽片，别相信文档。** AX301 的引脚标签在我们的 config 里就是错的；
   一次 4 烧录的硬件探针在 5 分钟里给出了正确答案。
2. **Bit-perfect ≠ 烧录可用。** 比特流可以在 CRAM 上字节相同，照样被芯片
   拒收 —— 因为 header CRC、frame CRC 或者别的配置阶段的校验结构不对。
3. **未知 CRC 用线性约束破。** 拿绝对 CRC 去暴力 65,536 个多项式会失败
   （自由度太多）；拿两段精心挑选的帧之间的**差**去暴力，搜索空间会瞬间塌缩。
4. **读写 codec 必须用同一套 baseline 约定。** Round-trip 读可能通过，
   但绝对硬件行为是错的 —— 只要双方共享同一个 XOR-delta 假设就抓不到。
   永远用物理行为验证，而不只是自洽。
5. **板子上一颗会动的 LED 顶得上一千个通过的单元测试。** 上面这些 bug 全都
   绕过了我们的软件检查，只在板子上 LED 表现错误的那一刻才暴露出来。

现在 codec 栈有了一条闭合回路：

```
Verilog 想法  →  LutCodec.write_tt  →  patch_rbf_crc  →  openFPGALoader
                                                              ↓
                                                     真实 EP4CE6 矽片
                                                              ↓
                                                     LED 按设计响应
```

从这一刻起，我们不再需要绕回 Quartus 来验证 codec 改动 —— 我们可以自己
写比特流，看着芯片回应。

### CRC 幽灵：一张「能通过测试」的映射表其实是假的（2026-04-08）

项目接近尾声时，我们差点把一张完全虚构的映射表当成里程碑庆祝掉。
下面用大白话把这件事记一下。

bitstream 的数据区被切成 1727 个「帧」，每帧 210 字节。每帧的**最
后 2 个字节是 CRC-16 校验码** —— 芯片用它来检测下载过程中有没有
比特被翻错。我们老早就知道这件事。

芯片内部的配置 RAM 也按列组织，每列也是每 210 字节一个周期（物理
尺寸决定的巧合）。所以很容易产生一个幻觉：「列内第 184 号字节」
看起来应该和「帧内第 184 号字节」是同一个字节。但它们不是 —— 列
的起点和帧的起点**不在同一个字节对齐**，中间差着一个偏移。结果
就是：一个按列坐标看是「pair 13，位置 184」的 cell，物理上可能落
在**某个帧的第 208 号字节** —— 那就是 CRC 字节。

过去一段时间，我们一直在用「XOR 两个 Quartus 编译出的 .rbf」的办法
挖「R24 switch 位」和「触发器控制位」。只要逻辑上改一个 bit，
Quartus 就会重新计算那一帧的 CRC，于是 XOR 差分里就会同时出现
**真正改掉的那一位** + **那一帧的两个 CRC 字节**。我们没察觉，
把 CRC 字节当成真实配置位记进了目录。我们骄傲地宣称「R24 switch
的 pair 间距是 419-420 字节」—— 其实这就是 2 × 210 = 420，**两
个相邻帧的 CRC 字节之间的距离**，跟 R24 结构半毛钱关系都没有。

铁证来自一行最简单的检查：对每一个「已映射」的 cell 问一句
`(offset - 32) % 210 >= 208`？如果成立，这个 cell 物理上就是一个
CRC 字节，而不是配置字节。结果触目惊心：

- `R24 I=0` 固定偏移表：**56 / 56 个 cell（100%）** 都是 CRC 字节
- 触发器异步复位控制 cells：**448 / 476 个（94%）** 是 CRC
- 触发器使能控制 cells：**168 / 168 个（100%）** 是 CRC

但路由合成器的 1725/1725 回归测试照样全绿。原因是我们在生成任何
.rbf 的最后一步都会调用 `patch_rbf_crc()`，它会根据帧内的数据字节
**重新计算并覆写**每一帧的 CRC 字节。所以 R24 写入的动作是：先把
CRC 字节翻一下，然后 `patch_rbf_crc` 立刻用正确的 CRC 把它覆盖
掉。这些写入等于没有任何效果。真正的 R24 位元其实是在别的路径上
（大概率藏在我们已经挖出的 LI 和 C4 envelope 里）被写进去的，所以
硬件路由照样工作。测试看起来是 bit-perfect，只是因为
`patch_rbf_crc` 幂等地替一条坏掉的写入路径擦了屁股。

我们已经把相关的 FASM 指令用硬报错禁用掉，把发现写进了项目
memory 作为 critical 警告，并排了一个 re-audit 任务 —— 用同一个
`(off-32) % 210 >= 208` 过滤器把 codec 里所有其他映射都审一遍。

### 修复：用 CRC 归一化的差分把 FF 控制位重新挖出来（2026-04-08）

CRC 幽灵发现的几个小时之后，我们用两个改动重新跑了一遍 FF 挖矿：
每个 .rbf 在做 XOR 差分**之前**都先经过 `patch_rbf_crc` 归一化（让
CRC 字节干净抵消），而且每种 variant 都编译多次，把 Quartus 的放置
选择平均掉。

Round 1 用 8 个不同的 `SEED` 值在同一个输出引脚上编译 {base, arst,
ena}。一个愉快的意外：对于一个琐碎的 D 触发器设计，8 个 seed 的
base-vs-base 差分是**零字节**。之前挡住我们的「fitter 噪声墙」原来
是带路由负载的设计特有的 —— 不是 Quartus 本身的性质。扣掉 CRC 字节
之后，arst 和 ena 各自都有 ~75-95 个 cell 在所有 8 个 seed 里都翻转。

Round 2 反过来固定 seed，换用 **10 个不同的输出引脚**，把 FF 散布到
芯片上 10 个不同的 LAB。把 round 1 和 round 2 的 universal 集合取
交集，得到的就是**既与 seed 无关、又与放置位置无关**的 cell ——
也就是真正的设备级 FF 控制位。

最后的数字是 **61 个 arst + 61 个 ena**，其中 arst ∩ ena = 48 个
共享的「任何带控制信号的 FF」使能位，各自有 13 个是模式专属的。
大多数落在比特流 header 段（偏移 < 5282，`patch_rbf_crc` 永远不动
这段），呈一个紧凑的位域：

- 偏移 73-74 是主 FF 模式字节；arst 用 bit {1,5,7} 和 {0,1,3,4,6}，
  ena 用同两个字节里的不同 bit 子集
- 偏移 42-52、710-729、1074-1081 是辅助位域

13 个落在 CRAM 段的 cell 在 10 个不同放置下都停在同一个绝对偏移上，
这说明 Quartus 永远把 FF 控制信号走一条**固定的全局时钟/复位网络**
—— 这 13 个 cell 配置的是那张网络，和具体哪个 LAB 无关。

这给了我们一个 FF 特性编码的三层图景：

1. **设备级控制特性位** —— 现在挖出来了（每种模式 61 个）
2. **per-LE 模式位**（*这个* LE 的 FF 用 arst）—— 还没做
3. **per-LE FF 存在位** —— 部分已经在 LUT codec 里

`fuzz/bitstream.py` 里的 `FFCodec` 改写成在 import 时加载
`results/ff_remine_final.json`，直接翻这 61 个绝对偏移。round-trip
测试证实 `FFCodec.write_arst(base)` 在所有 61 个全局位上都能和真实
Quartus 编译出来的 arst .rbf 完全一致。FASM 的 `DFF.ARST` / `DFF.ENA`
指令还是禁用状态，等 per-LE 挖矿完成再开。

旧的列相对 `_FF_ARST_CELLS` / `_FF_ENA_CELLS` 表作为 deprecated
stub 留在文件里，前面加了注释指向 CRC 幽灵的 memory 笔记，让后来
读历史的人能同时看到错的答案和对的答案。

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
- [x] Phase 3.4：R4 I-index 映射 — 18/37 个已映射（13 个走 R4_BASE_PREV slot/group 公式：I=0,1,2,4,7,10,14,15,17,18,20,22,25；+5 个走逐 (X,I) 语料挖掘：I=3,11,12,13,16）
- [x] Phase 3.5：LOCAL_INTERCONNECT 开关建模（70% 交叉验证，22 列，4 种 pair 激活模式）
- [x] Phase 3.6：布线编解码器（RouteCodec 读写方法：C4/R4/LOCAL_INTERCONNECT）
- [x] Phase 3.7：R24 I=0 固定字节模型（~66% pair-diff 准确率，覆盖 73% 的 R24 线网）
- [x] Phase 3.8：C4 I≠0 逐 (X,I) 固定字节查表（24 条映射，11 个 I-index）
- [x] Phase 3.9：RouteCodec 往返自洽（列、行路径均 0 dropped、0 hallucinated）
- [x] Phase 3.10：LOCAL_INTERCONNECT base 粒度读 API（每 (pair, base) cell 单独发一条）
- [x] Phase 3.11：LI 编码模式破解 —— paired vs alternating，统一 9-cell envelope
- [x] Phase 3.12：硬件安全防线 V2（带特征识别的 `validate_safe_for_hardware`）
- [x] Phase 3.13：AX301 端到端硬件验证（编解码器 → 烧录 → 逻辑行为正确）
- [x] Phase 3.14：路由综合跳岛策略 —— **15 座绿区源 LAB**（(4,4)、(10,4)、(10,10)、(10,14)、(13,10)、(16,4)、(16,8)、(16,14)、(19,14)、(22,12)、(22,16)、(25,6)、(28,10)、(28,18)、(31,12)），**686/686 路由对 Quartus bit-perfect**，指纹漂移 = 0
- [x] Phase 3.15：**EP4CE6 RBF CRC 完全逆向**（CRC-16/IBM，poly 0x8005，init 0xFE54，反射，每 210 字节一帧，frames 25..1751）。CRC patcher 已整合进 codec；1727/1727 CRAM 帧验证通过
- [x] Phase 3.16：**硬件回环闭合** —— RouteCodec + LutCodec 输出经 CRC patch 后可直接烧入真实 EP4CE6 矽片（不再回退到 EPCS）
- [x] Phase 3.17：AX301 引脚映射经 `pin_probe.py` 在矽片上验证（KEY1=E15、KEY2=E16、KEY3=M16、KEY4=M15、LED0=G15）
- [x] Phase 3.18a：**EP4CE6 ≡ EP4CE10 确认是同一颗物理矽片** —— RBF 逐字节相同（含 device ID）；CE10 可作为「越狱版 Quartus」用来 fuzz CE6 的禁区（`fuzz/cross_device_diff.py`）
- [x] Phase 3.18b：**完整越狱 —— CE6 版图白名单被证伪** —— 三阶段 XOR 链坏点扫描器硬件验证 2,480 颗禁区 LE 全部健康（`jailbreak/scanC_gen.py`）；解锁 6 条新 LAB 列（X=5,9,14,30,32,33）+ Y=15 整行；有效 fabric 392→520+ LAB、6,272→10,320 LE (+65%)
- [x] Phase 3.18：**4 输入 LUT 功能 demo 在硬件上跑通** —— `LED0 = (K1∧K2)∨(K3∧K4)`，由 LutCodec 写入，按键按下完整真值表验证通过

### 进行中

- [~] Phase 3.19：映射剩余 R4 I-index —— **37 个中已映射 24 个**（I=6 于 2026-04-08 移除；同日复审发现 I=6 和 I=8 都是非 LAB CRAM，需要不同的列模型）。同日 `fuzz/r4_remine.py` 分析式复审（942 条 STA 语料 × `route_cells.json` 绝对 cell 集，零差分偏差）**翻案**早上的 per_route_delta 审计：I=0/1/2/4/7/10/13/15/16/17/18/20 命中率 60-97%，**LAB-CRAM 条目整体健康**。确认有问题的：I=12（29%）、I=14（(3191,3191) 明显坏掉）、I=6/I=8（非 LAB CRAM）。R4 公式没被 `route_synth` 使用是因为 signature 后端短路，不是因为坏掉。剩余 13 个未映射：5,9,24,28,29,30,31,32,33,104,116,125 —— 被 STA 语料挡住
- [ ] Phase 3.20：M9K/DSP 边界列修复（X=13/26 等大列需要子区域地址模型）
- [ ] Phase 3.21：C16 长距离线建模（完全未映射）
- [x] Phase 3.22：**LI 模式选择规则 —— 阴性收案**。T9 + T10 正交网格语料（12 个 source、374 次 compile、414 条 mappable rows，`fuzz/li_mode_grid_mine.py` + `li_mode_analyze.py` + `li_mode_tree.py`）。可部署规则：`dy∈{2,3,21}→edge_even_b0`（100%）、`adx==0→paired`（79%）、`dx>30∧dy>7.5→paired`。中段叶子 `dy>3∧dx≤24.5∧adx>0.5`（n=247，占语料 60%）卡在 **52% 抛硬币**，语料翻倍 + 强制 sx/dx 解耦都没用。结论：paired vs alternating **不是静态路由键的函数**，大概率是 Quartus 的 placement seed / LI 通道占用 / 成本函数 tiebreak 决定的。继续扩语料不会有帮助。黄区回退继续把 `paired` 作为弱先验（两种模式都是硬件安全的）。
- [x] Phase 3.23：**C4 I≠0 大扫** —— `fuzz/c4_inz_sweep.py` 从现有 routing_paths 语料里挖出 19 条新的 (X,I) 映射，`_C4_FIXED_OFFSETS` 从 25 条扩到 **44 条**。绿区回归仍然 58/58 bit-perfect。
- [x] Phase 3.24：**非 LAB 列身份解密** —— `jailbreak/probe_blocks.v`（12 个 altsyncram + 8 个 lpm_mult，虚拟管脚）。Quartus 把 block 分别落在 `M9K_X15_Y*`、`M9K_X27_Y*`、`DSPMULT_X20_Y*`。越狱之后的 3 条真·非 LAB 列身份确认：**X=15、X=27 是 M9K RAM 列**；**X=20 是嵌入式 9×9 乘法器列**。PLL 不占任何 X 列，在 die 边缘。
- [x] Phase 3.25：**越狱版图在矽片上完整收案（2026-04-07）** —— 两个轴都通过编解码器端到端在矽片上验证。**X=32 列**：LCCOMB_X32_Y10_N0 mask 0x8888 在 AX301 上跑通；编解码器已校准，`COLUMN_BASE` 扩展到全部 28 条 LAB 列，标准 7350 字节步进。**Y=15 幽灵行**：LCCOMB_X10_Y15_N0 mask 0x0357 = `(K1∧K2)∨(K3∧K4)` 在 AX301 上跑通（`fuzz/demo_y15_keys2led.py`）。+65% fabric 在真实 CE6 矽片上达到生产可用
- [x] Phase 3.26：**路由综合绿区从 3 → 15 个源 LAB**（`fuzz/fingerprint_raw_mine.py` 编解码器盲态 XOR 挖掘 + 头部过滤）；686/686 路由 bit-perfect。`results/r4_iindex_table.json`（942 条目）由 `route_synth.py:206` 静默使用，按 (src,dst,port) 几何选择 R4 I-index 提示
- [~] Phase 3.27：**M9K CRAM 探测 —— 已被 Phase 5.0 取代**。旧版 `m9k_probe_mine.py` 归档的 237/299 cell，经 Phase 5.0 证实 76-81% 是 CRC byte ghost，CRC-strip 后各剩 58 cell 且 `GLOBAL_ON` 与 `COL15_ON` 完全相同 —— 「列特定」签名从未存在。Y 位置模型依旧放弃；STA wire 法也证实死路（见 Phase 5.0）

- [x] Phase 5.0：**非 LAB 块（DSPMULT + M9K）实物 pin 重挖，2026-04-08**。LOC 语法破解（`fuzz/{mult,m9k}_loc_discover.py`）：LOC 吃的是 MegaFunction 的分层节点路径，不是坐标别名 —— DSPMULT 用 `lpm_mult:u|mult_qpl:auto_generated|mac_mult1`，M9K 用 `altsyncram:u|altsyncram_3ov:auto_generated|ALTSYNCRAM`，42 个合法 DSPMULT 点位（Y1..21 × N{0,1}）+ 126 个合法 M9K 点位（X∈{15,27}）。**确立两条强规则**：
  - *严禁用 VIRTUAL_PIN 挖非 LAB 块* —— 首次 62 cell 的 `MULT_GLOBAL_ON` 在 VIRTUAL_PIN 下挖到，与实物 pin 重编译 0 重叠，证实是 Quartus 假管脚幻影布线，retag 成 `MULT_VIRTUAL_PIN_ARTIFACT`（`fuzz/mult_noise_test.py`，记忆体 `feedback_virtual_pin_mining_is_fiction.md`）
  - *非 LAB 挖掘必须 CRAM-only 过滤（off≥5282）* —— 5-seed 零假设测试（`fuzz/mult_header_noise.py`）证实 byte 44 和 byte 73 每次编译即翻 **4-5 bit seed noise**，每一种非 LAB 块都会动 **加上** FF arst/ena 也动这个区段。任何 header-band「发现」不过滤就是谎。杀了 `fuzz/mult_param_sweep.py` 挖到的 `SIGNED_CORE = 4 cells`，同时把 FF layer-1 byte 44/73 的条目也列入待复审（记忆体 `feedback_header_band_noise_floor.md`）
  - **成果**（CRAM-only + CRC-strip）：`MULT_GLOBAL_ON_REAL` = **29 cells**（42 点位实物 pin 扫）；`M9K_GLOBAL_ON` = **58 cells** CRC-strip 后的净值，与 126 点位实物 pin 重扫交叉验证 55/58 命中；`MULT ∩ M9K = 0`（块间完全不共享）；X=15 与 X=27 的 universal 字节一致，再次确认无列特定签名
  - **发现两条非 LAB 配置带**：(1) **块启用/模式带，frames 1692-1738**，容纳 mult 29 + M9K 58 且位置两两不相交；(2) **块时钟网带，frames ~1007-1013** —— `fuzz/mult_reg_sweep.py`（`lpm_pipeline` ∈ {1,2,3}）挖出**首个**单 bit 语义字段 `DSPMULT_CLOCK_ENABLE = (209891, bp 4)`，且 M9K 每点位的 4 个时钟 bit 在 frames 1010/1013 同 bp=4 距离 mult 时钟 bit **仅 1-3 byte**，属于槽位保留式每块时钟暂存器
  - **死路**：STA wire 抽取（`fuzz/mult_sta_wires.py`）只返回 chip-edge IOBUF —— Quartus 把 DSPMULT 当黑盒 cell，内部布线不暴露给 `report_timing`；width/signed/pipeline 除 CLOCK_ENABLE 外都埋在 header 噪声里；`altpll` 无 X/Y LOC（片上外设，用 `PLL_1`/`PLL_2` 单例名），暂缓

- [x] Phase 4：**FASM 工具链在矽片上收案（2026-04-08）** —— `fuzz/fasm2rbf.py` + `fuzz/rbf2fasm.py` 实现最小 FASM 方言（`LUT`、`ROUTE`、`BIT`、`SRC`），驱动 `LutCodec` + `RouteCodec` + `patch_rbf_crc`。signature 后端（`fuzz/route_signatures.py`，**1725** 条路由 cell-set）对黄区和 Y=15 越狱源直接短路 `synth_route`。**Port-MUX 合并版 loader（2026-04-08）**：每个 `(src,dst,dn)` 组分解为共享 `common` 前缀 + 每个 port 恰好 4 个 delta cells（2 对相邻字节对，相距 840 字节 = LI-pair×4）。225/225 个完整 4-port 组符合「3+1」等价类，datab 永远是独立端口。`route_signatures.load_cells()` 优先加载 `results/route_cells_consolidated.json`（34% 文件 / 37% cell 压缩），语义不变式 `common ∪ port_delta[p] == route_cells[key+",p"]` 自检 1725/1725。set-cover 分解器（`fuzz/route_decompose.py`）把多路由 + 跨 source 的 CRAM diff 折叠成干净的 directives。回归：单路由 **1725/1725**、多路由 41/42（1 个先存在）、跨 source 3/3、绿区 15/15 岛屿（686/686）—— 全部 bit-perfect。硬件收案：`X10Y10N0.LUT = 0x8888`（AND(K1,K2)）一行 FASM 经 `fasm2rbf` 烧到 AX301，矽片行为一致

### 未来工作

- [ ] Phase 5：完善布线编解码器覆盖率（目标：所有线类型 >90%；C16 + 剩余 R4 I-index 仍未结）
- [ ] Phase 6：NextPNR EP4CE6 后端开发（从 bit dictionary 生成 chipdb + nextpnr-generic 对接）

### 长期方向：我们究竟可能在哪里赢过 Quartus

一个常被问到的问题是：「现在 codec 已经能跑了，能不能用现代 ML（RL 路由、
GNN 拥塞预测、LLM 逻辑综合）超越 Intel Quartus？」基于这个项目目前的真实
状态以及学术界文献，我们的诚实答案是：**对大多数人首先想到的方向是不行
的，但对一组更窄、更有意思的目标是可以的。**

**我们赢不了的地方。** Quartus 拥有硬件校准过的时序模型（每根 wire 的 RC
都在真实矽片上跨 process corner 测过）、30 年累积下来的完整 legality
checker，以及 PathFinder + negotiated congestion 路由算法 —— **截至 2024
年，学术界的 RL 路由器在标准 benchmark 上还没有稳定超越过 VPR**，更别说
Quartus。试图用强化学习在 Quartus 主场把它的路由打趴是一个众所周知的学术
陷阱。

**我们能赢的地方。** 我们手上有一个 Quartus 没有也永远不会有的不对称
优势：**一个可程式、bit-level、双向的编解码器，能在微秒级修改比特流，并
在数秒内于真实矽片上验证结果。** Quartus 是一个单向的 `verilog → bitstream`
黑盒；我们不是。这条鸿沟带来了 Quartus 在结构上做不到的几件事：

1. **比特流级别的 superoptimizer（CRAM peephole 优化）。** 拿一个 Quartus
   build 出来，逐 cell 做等价变换（等价 LUT mask 替换、冗余布线 bit 移除、
   并行 LE 合并），在硬件上验证等价性，接受能降低 cell count / 动态功耗的
   变换。Quartus 一旦 fit 完就不会再回头微调；我们可以离线跑数千次硅片
   验证过的小变换。这个胜利来自「真实矽片上无限次免费试错」，**不是来自
   更聪明的模型**。
2. **Quartus 根本不会做的事。** 我们的 codec 让以下事情成为可能：
   - 在不官方支持 partial reconfiguration 的晶片上做 PR（不重启地改写
     特定 frame）
   - Bitstream watermarking / fingerprinting（藏 ID 在无关紧要的 LUT bit）
   - 可重现构建（Quartus 依赖随机种子；我们的 codec 是纯函数 —— 同样的
     输入永远输出 bit-identical 的结果）
   - 单晶片过拟合（针对某一颗具体晶片的 process corner / 老化校准 —— 对
     硬件安全和 PUF 有用）
3. **开源工具链（真正的奖品）。** 一条能跑通的 Yosys + nextpnr-EP4CE6 流程
   比「在 PPA 上打败 Quartus」**重要 100 倍**。它让 Linux/macOS 用户第一次
   能在不装 Intel 工具的情况下用这颗晶片，让 CI 系统第一次能可重现地构建
   EP4CE6 比特流，让这颗晶片第一次进入开源 FPGA 生态。**这才是这个项目
   真正的长期目标。**

**ML 该扮演什么角色（助手，而不是核心）。** 现代 ML 在这个项目里有真实
但有限的位置：

- **决策树模式分类器** 替代手写的 LI envelope 规则
  （`_classify_li_lab()`）。语料够大之后，学出来的分类器比硬编码模式更
  robust，而且仍然完全可解释。
- **模式挖掘器** 用在 `li_mode_corpus_mine.py` 的输出上 —— 找
  paired-vs-alternating 的选择规则用的应该是小决策树而不是 GNN。决策树
  可以审计、可以直接编进 codec。
- **异常检测器** 用在烧不上去的 codec RBF 上 —— 预测最可能违反了哪个
  envelope，加速 debug。

这些都不是「ML 打败 Quartus」。它们是「ML 帮我们学一些我们不想手动推的
规则」。

**建议优先级。** 先把 Phase 5–6 做完（布线覆盖率 → chipdb → nextpnr 后端）。
一旦端到端的 `.v → bitstream` 开源流程能跑起来，问题就从「能不能在 PPA 上
打败 Quartus」变成「我们能做哪些 Quartus 根本做不了的事」—— 而解锁这些
答案的是 codec，不是模型。

> **一句话总结 —— 我们不是在造一个更聪明的 Quartus。我们是在造一种不同
> 的工具，让用户能做一些 Quartus 根本不让他们做的事情。胜利在于定义一个
> 新的赛场，而不是在 Quartus 的主场上击败它。**

### 整体进度估算

| 领域 | 进度 | 说明 |
|------|------|------|
| 逻辑配置（LUT/FF/算术） | **~95%** | 全部 LE 位置的 LUT TT 已解码，FF 和算术模式已映射 |
| CRAM 地址映射 | **100%** | 22 列 × 18 行 × 16 LE = 376/376 位置全部验证（CE6 白名单；越狱后 X=32/33 + Y=15 矽片验证通过） |
| C4 布线开关 | **~55%** | I=0 100% 公式；I≠0 44 条逐 (X,I) 固定字节查表 |
| R4 布线开关 | **~68%** | 25/37 个 I-index 已映射，剩余 12 条卡在语料不足而非挖掘方法 |
| LOCAL_INTERCONNECT | **~85%** | base 粒度读写；两种编码模式破解；V2 硬件安全防线 |
| R24 长距离线 | **~30%** | I=0 固定字节模型，覆盖 73% R24 线网 |
| C16 长距离线 | **0%** | 尚未开始 |
| 比特流编解码器 | **~85%** | LUT TT + 布线读写完成；往返自洽；硬件安全防线 V2；**CRC patcher 已整合，硅片端到端通过** |
| 路由综合（绿区岛） | **15/392 源** | (4,4)、(10,4)、(10,10)、(10,14)、(13,10)、(16,4)、(16,8)、(16,14)、(19,14)、(22,12)、(22,16)、(25,6)、(28,10)、(28,18)、(31,12) — 686/686 路由对 Quartus bit-perfect |
| FASM signature 后端 | **1050 条路由** | `results/route_cells.json` —— 对全部挖到的路由（含黄区 + Y=15 越狱行）短路 `synth_route` |
| RBF CRC 逆向 | **100%** | CRC-16/IBM 0x8005，init 0xFE54，frames 25..1751；1727/1727 帧验证 |
| FASM 工具链（Phase 4） | **闭合** | `fasm2rbf` + `rbf2fasm` + 集合覆盖分解器 + port-MUX 合并版 loader（34% 压缩）；1725/1725 + 41/42 + 3/3 + 686/686 bit-perfect 回归；AX301 矽片接受（AND(K1,K2)） |
| 硬件回环（codec → 烧录 → 矽片） | **闭合** | LutCodec 与 FASM 路径都在 AX301 上跑通 |

---

## 参考资料

- [Cyclone IV Device Handbook](https://www.intel.com/content/www/us/en/docs/programmable/683853/current/cyclone-iv-device-handbook.html)
- [Project IceStorm](http://www.clifford.at/icestorm/) — iCE40 逆向工程，方法论范本
- [Project Mistral](https://github.com/Ravenslofty/mistral) — Cyclone V 逆向工程，同家族参考
- [Quartus Prime Lite](https://www.intel.com/content/www/us/en/products/details/fpga/development-tools/quartus-prime/resource.html) — 免费 FPGA 开发工具

---

## 许可证

**双许可证（2026-04-07 起，替换原先的 MIT）：**

**为什么换。** 项目大部分时间用的是 MIT —— 研究性小代码的默认选项。
真正让我们改主意的，是上面那一节《完整越狱：CE6 的版图是一场集体
造假》里记录的 CE6→CE10 越狱结果。在那之前，这些发现看起来只是
针对一颗入门级 FPGA 的窄范围逆向；但当我们在矽片上亲手证明 —— Altera
以 EP4CE6 之名卖出的这颗芯片物理上就是一颗 EP4CE10、fitter 白名单
删掉了整整 ~40% 的 die、藏起来的 2,480 颗 LE 一次通电就全部正常 ——
游戏的赌注就变了。这份代码和这些发现不再只是「便宜板子上的小把戏」，
而是一份能让全世界的 EP4CE6 板子多掏出 ~65% 逻辑资源的开源工具链
雏形，也是一份可复现的、能逮住厂商未来对其他型号玩同样手段的方法论。
挂 MIT 的话，Altera 可以把这套方法默默吸收进 fitter 补丁，一句话
都不用说。GPLv3 + CC BY-SA 强迫所有下游 —— 商业的、学术的、甚至厂商
自己 —— 继续坐在同一张开放的桌子上，附完整源码和完整出处。这才算
是对矽片刚刚告诉我们的事情的诚实回应。



- **代码** —— `GPL-3.0-or-later`。Python pipeline、Verilog 生成器、
  codec 实作、越狱扫描器，以及 `fuzz/` 底下的所有东西都是 copyleft。
  如果你把这份代码 vendor 进另一个工具链 —— 开源或闭源、爱好或商业，
  甚至是 Altera/Intel 的官方工具 —— 你的项目也必须以 GPLv3 发布，
  附完整源代码。完整文本：
  [`LICENSES/GPL-3.0-or-later.txt`](LICENSES/GPL-3.0-or-later.txt)。
- **文档、发现与方法论** —— `CC BY-SA 4.0`。CRAM 模型、C4/R4/LI 位址
  公式、RBF CRC 规格、CE6→CE10 越狱结果、XOR 链坏点扫描法，以及
  `README*.md` / `CLAUDE.md` / `FINDINGS.md` 里的全部论述，都采用
  share-alike。如果你在论文、教程或演讲里引用这些发现，你的衍生作品
  也必须挂 CC BY-SA。完整文本：
  [`LICENSES/CC-BY-SA-4.0.txt`](LICENSES/CC-BY-SA-4.0.txt)。

范围说明见 [`LICENSE`](LICENSE)。

选这两个许可证是刻意的：这项工作存在的目的是把 FPGA 工具链的研究
**留在骇客手里**。MIT 会让 Altera 悄悄打上 fitter 白名单的补丁、
把这些发现吸收进闭源产品，而无需任何回馈。GPLv3 + CC BY-SA 强迫
所有下游 —— 商业或学术 —— 继续留在同一张开放的桌子上。

Bitstream 原始档（`*.rbf`、`*.sof`）、原始 SQLite 资料库，以及
`work/` 和 `results/rbf/` 里的 Quartus 编译产物属于硬件遥测数据，
不是创作品，本项目不对它们主张版权；其再分发仍受原厂家授权条款
约束。

本项目仅用于教育和研究目的。逆向工程的结果用于构建开源 FPGA 工具链。
