# EP4CE6 Bitstream 逆向工程

## 这是什么项目？

这个项目的目标是**完全逆向工程** Altera（现 Intel）Cyclone IV 系列 FPGA 芯片 **EP4CE6F17C8** 的比特流（bitstream）格式。

给首次接触 FPGA 的读者：比特流就是配置可编程逻辑的那个文件——对于
Altera 的芯片而言是 `.rbf`（Raw Binary File）。背景资料：[Cyclone IV
device handbook](https://www.intel.com/content/www/us/en/docs/programmable/683853/current/cyclone-iv-device-handbook.html)。

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

| 项目 | 目标芯片 | 核心贡献 | 与本项目的关系 |
|------|----------|----------|----------------|
| [Project IceStorm](http://www.clifford.at/icestorm/) | Lattice iCE40 | 完整的开源 bitstream 工具链（`icebox` / `icepack`）以及奠基性的黑盒 fuzzing 方法论 | 方法论范本；我们的 fuzz 流程与验收标准直接继承自 IceStorm |
| [Project X-Ray](https://github.com/SymbiFlow/prjxray) | Xilinx 7-series | 定义了 FASM（FPGA Assembly）格式，以及 specimen fuzzer + 差分提取的挖掘范式 | 我们的 `fasm2rbf` / `rbf2fasm` 直接沿用 FASM 格式与目录结构 |
| [Project Mistral](https://github.com/Ravenslofty/mistral) | Altera Cyclone V | 从 `quartus_cdb` + Tcl 导出 RBM 模型；首个开源的 Cyclone 系列逆向工程 | 同家族芯片 —— CRAM 分层与路由开关术语与 Mistral 相当近亲 |
| [Project Trellis](https://github.com/YosysHQ/prjtrellis) | Lattice ECP5 | Diamond fuzzing + 按 cell 分解路由 bit + 与 nextpnr-ecp5 深度整合 | 我们的 chipdb 生成与 nextpnr-generic 整合参考了 Trellis 的模式 |

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
├── synth/                  ← 开源工具链（Yosys + nextpnr-generic）
│   ├── ep4ce6_map.v        ← Cyclone IV techmap（LUT4/DFF 原语）
│   ├── prims.v             ← nextpnr-generic 原语库
│   ├── m9k.lib             ← M9K BRAM 库桩
│   ├── synth_ep4ce6.ys     ← Yosys 综合脚本（NEORV32 源码路径使用 $HOME）
│   ├── synth_ep4ce6.sh     ← 包装脚本 —— 跑这个而非 .ys；会用 envsubst 展开 $HOME / $NEORV32_ROOT
│   └── np2fasm.py          ← nextpnr 布线 JSON → FASM 转换器
├── jailbreak/              ← CE10 fitter 探针（X=32/33、Y=15 坏点扫描）
├── results/
│   ├── rbf/                ← 收集的 .rbf 文件（~2,500 个，各 368 KB）
│   ├── fingerprint_*.json  ← 15 个绿区 island 语料
│   ├── route_cells_full.json ← 13,487 条 sig-cache（7-tuple，Plan D' + legacy）
│   ├── route_cells_consolidated.json ← port-MUX 合并版 loader
│   ├── nv_fingerprints/    ← NEORV32 per-source 指纹
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
7. **追 codec bug 之前先和 Quartus 对一下** —— 如果一个设计在开源工具链里不工作，先让 Quartus 编一份同样 Verilog 的参考 RBF 烧进去。如果 Quartus 版能跑而你的不能，**然后**再去对比 cell diff 判断差异是否集中在你意想之中的区域。M5 计数器事件里，我们花了好一段时间追五个"真实但无关"的低层 bug，就因为少做了这个 30 秒的实验 —— 问题根本不在 codec，而在 nextpnr-generic 没有 carry chain primitive
8. **自环 sig-cache 条目在当前挖矿模板下不可修复** —— 对于 src LE == dst LE 的路由（LE 反馈到自己的某个 dataX 输入），双 LUT 配对模板从结构上就无法表达；diff-vs-baseline 策略也会失败，因为 Quartus 在两次编译间会重新 fit（包括重新分配管脚）。任何依赖自反馈的设计（典型例子：不走 carry chain 的 ripple 加法器）在 Phase 5.4 完成之前都无法通过开源工具链生成有效比特流 —— 暂时用 Quartus 的参考 RBF 代替

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

### Phase 4.5 —— 把 FASM 链路放大到真实设计（2026-04-09）

在 Phase 4 我们已经证明一行 `X10Y10N0.LUT = 0x8888` 的 FASM 源文件能
被编译、烧录、在真实的 AX301 矽片上运行。这是一个重要里程碑，但它
有一个隐性局限：我们的 signature 缓存 `route_cells.json`（1725 条
目）是在 **只 15 个「绿区」LAB 位置** 挖出来的，并且源 N 全部等于
0。而像 NEORV32 这样的真实 CPU 设计，逻辑单元散布在整片晶片上，每
一个偶数 N 槽位都可能塞着触发器，有反馈路径，有布线枢纽，没有一块
长得像我们那 15 个训练岛。我们怎么知道链路能泛化？

Phase 4.5 就是这个「放大」实验。目标：**能不能让 FASM 链路在矽片上
逐字节复现一条来自真实 NEORV32 编译的 edge，包括 Quartus 官方禁区
的「越狱」列？**

#### 什么是「signature 缓存」？

在回答之前，先说清楚我们的缓存到底是什么东西。它 **不是** 一个解
析公式。当我们说「路由 `X5Y3N4 → X4Y3N6.datad` 对应以下 144 个
CRAM cell」时，我们不是用几何公式算出来的 —— 我们是在一份 Quartus
为这条确切路由产生的真实 RBF 里 **观察到** 这 144 个 cell，然后把
观察记录存进了一个很大的 JSON 字典。缓存的 key 是路由 tuple，value
是 `(byte_offset, bit_position)` 二元组的列表，也就是 Quartus 为了
实现这条路由翻转过的所有位。

这和 IceStorm 的 fuzzing 方法是一套思想，只是粒度不同：IceStorm 问
「这个特性控制哪些位？」，我们问「这根从 A 到 B 的线需要哪些
位？」。烧录时我们不需要知道这些位 *为什么* 是这些位 —— 直接从缓存
里拷出来、XOR 进 baseline 就行。

代价是：缓存只认识它见过的路由。要让它覆盖 NEORV32，就必须把
NEORV32 用到的每一条 edge 都编译一次。

#### Plan D' —— 一座 12,000 次编译的工厂

第一步是 dry-run：我们 parse 了 NEORV32 的 static-timing 报告
（`quartus_sta` 吐出来的 3.6 GB 文本），抽出编译器实际用到的每一条
路由 edge。去重、去自环以后剩下 **12,259 条独立 edge**，每条都是一
个 7-tuple `(sx, sy, sn, dx, dy, dn, port)`。这是「订单清单」。

第二步是工厂本身：`fuzz/plan_d_prime_factory.py`。它起 12 个并行的
Quartus worker 进程，每次分一条 edge 给一个 worker。worker 写一段
最小的双 LUT Verilog（`lut1 → lut2` 加一个 clock register 防止
Quartus 把它优化掉），把两个 LUT 强制放在 edge 指定的坐标，跑完整
的 Quartus 编译，把产物存成
`nv_pair_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}_{port}.rbf`。工厂开跑
前会先把双 LUT 模板物理上 place 不了的 edge 过滤掉：N-normalizer
折出来的奇 N 自环、IO-ring 坐标、非 LAB 列（X ∈ {15, 20, 27}，
M9K 和乘法器块）。12,259 条原始 edge 降到 **11,762 条可 place
edge**，剩下的 497 条在这种策略下无法表达，不是遗漏。稳态速率
~0.28–0.29 编译/秒，最终一轮以 **11 小时 16 分钟零失败** 走完整
份清单（本轮 11,715 ok / 0 fail，另加磁盘上来自早前部分 run 的
47 条可 place edge）。

每个编译完成的 RBF 都和一个中性 `nv_zero_global.rbf` baseline 做
XOR-diff，diff 出来的 cell 按 edge 7-tuple 存进
`results/nv_route_cells.json`。这份文件再和旧的绿区缓存合并成
`results/route_cells_full.json` —— 统一的 7-tuple sig-cache，key 是
`"sx,sy,sn->dx,dy,dn,port"`，**合并后 13,487 条**。旧的 6-tuple 条
目在合并时自动补上 `sn = 0`，保证原来的绿区回归测试一行代码不动就
能继续通过。把合并后的缓存与完整的 12,259 条 NEORV32 订单清单对
照，覆盖率是 **11,762 / 12,259（95.9%）—— 也就是工厂能 place 的每
一条 edge 都覆盖到，达 100%**。那 4.1% 的缺口正好是前面说的 filter
集，不是工厂的遗漏。有意思的是，**1725 条绿区旧条目对 NEORV32 命
中数为零** —— 所有覆盖都来自 Plan D' 工厂新生成的条目。旧缓存仍然
留在合并文件里，因为它对绿区回归测试套件仍然承重，但对真实设计而
言已经是死重。参见 `memory/legacy_cache_zero_nv32_hits.md`。

#### 为什么 source-N 这一维必须保留

一个常见的问题：为什么 key 里一定要带 `sn`？不能用
`(sx, sy, dx, dy, dn, port)` 就好吗？

答案是真实 CPU 里每个 LAB（逻辑阵列块）有 16 个 LE 槽位，不同槽位
有不同的下游布线外壳。一个从 `N=14` 出来的触发器用的 switch-box 和
一个从 `N=4` 出来的组合单元不一样，哪怕两个都住在 `X=5, Y=3` 又都
打到同一个 destination port 也不一样。把这两条折叠进同一个 key
会让缓存在其中一条上给出错误答案。保留 `sn` 要多花几 MB 的 JSON，
换来的是任何 `N≠0` 的源都能正确工作。

#### 英雄测试：X=5、sn=4、上矽片

工厂热起来以后，我们挑第一条同时满足三个条件的 edge：**(a)** 源头
在 CE6 白名单之外的「越狱」列（需要对 Quartus 谎称晶片是 EP4CE10
才能 place 上去）；**(b)** 源 N 非零（确保真的走 7-tuple 路径，而不
是回退到 `sn=0` 的 legacy lift）；**(c)** 工厂已经编译过这条 edge，
磁盘上有对应的 `nv_pair` RBF 可以作为 ground truth 来对拍。

挑出来的 edge 是 `ROUTE X5Y3N4 -> X4Y3N6.datad`。源头 X=5 是
Quartus CE6 软件白名单禁止的列 —— 它会直接拒绝在 X=5 上 place 任何
LUT。但我们早就从 2026-04-07 的越狱 probe 知道 X=5 在矽片上完全可
用，限制纯粹来自软件。Plan D' 通过谎报晶片型号的方式把路由打穿了
X=5。

英雄测试的 FASM 源码就 **一行**：

```
ROUTE X5Y3N4 -> X4Y3N6.datad
```

这行喂给 `fasm2rbf.py`，它在合并后的 cache 里查 7-tuple key，拷出
找到的 144 个 cell，XOR 进 `nv_zero_global.rbf`，逐帧 patch CRAM
CRC，写出一份 368,011 字节的 RBF。我们把这份 RBF 和工厂的 ground-
truth `nv_pair_X5Y3N4_to_X4Y3N6_datad.rbf` 逐字节对比：

```
CRAM 段（字节 ≥ 5282）:      0 字节不同  ← 完全吻合
Header 段（字节 < 5282）:    6 字节不同  ← Quartus 器件 ID / 种子
CRC 校验失败帧:              0 / 1727    ← 全部通过
```

CRAM 是 FPGA 配置状态机真正校验的那一段。**零 CRAM 差异** 意味着我
们 FASM 生成的 RBF 在功能上和 Quartus 自己的输出一模一样。另外六
个 header 差异落在字节 43–74，那里存的是 Quartus 的编译时间戳和
种子哈希 —— 配置状态机从来不看。

我们用 `openFPGALoader` 把 FASM 生成的 RBF 烧到 AX301。烧得很干
净，`Done`，没有 CRC 错，没有回落到 EPCS，FPGA 按两个 LUT 的常数
输出稳定地驱动了 LED pin。**第一次在矽片上证明**：

1. `fasm2rbf` 能从 7-tuple 缓存命中还原出工厂级别的 CRAM
2. Plan D' 的 cell 在训练语料之外仍然被矽片接受
3. CE6 禁区的 X=5 列在 FASM 控制下能完成配置并运行

一次烧录验证了整条链路。

#### 两个值得记住的负面结果

**负面结果 1 —— 被动挖 R4 暗号指不可行。** 我们的布线位模型
`_R4_BASE_PREV` 理论上有 37 个 R4 switch I-index，已经挖到 24 个；
剩下 13 个「暗」I-index 从来没在绿区语料里出现过，因为 Quartus 在
低布线压力下从来不选它们。我们原本指望一份在真实拥塞下编译出来的
完整 NEORV32 RBF 能把这些暗 I-index 点亮，让我们通过对比中性
baseline 恢复出它们的 BASE 地址。结果不行。NEORV32 的 diff 集太稠
密（113k 个 cell，约占全部 CRAM 位的 4%），以至于 *任何* 候选
BASE 在所测试 wire 上的命中率都能靠巧合达到 55–61%。null test 确
认这个方法连已知正确的 I=0、I=1、I=2、I=10 的 BASE 都还原不出来。
**教训**：被动观察需要稀疏信号。稠密 diff 会把你想找的图案淹没掉。

**负面结果 2 —— 「高扇出源先跑」的直觉是错的。** 工厂跑到 22% 的
时候，我们问了一个问题：剩下的 9,500 次编译如果按源的 fanout 从大
到小重排，能不能更快达到英雄测试要的「源完整覆盖」里程碑？直觉是
「先铺主干道，再修小巷」—— 大枢纽先做完，小叶子源可以等。我们写
了一份纯模拟器（完全不影响正在跑的工厂）来跑数据。结果和直觉相
反：fanout-first 的顺序让「源完整覆盖」这个指标 **延后最多 4.2 小
时**，相比目前的字典序。原因是工厂花 12 分钟啃一个 203 条 edge 的
大枢纽源时，字典序在同样的 12 分钟里能跑完 ~60 个小源。字典序碰巧
把小源聚在排序列表的头部，对这个指标几乎是全局最优。**教训**：在
没有模拟器证明新顺序在目标指标上严格更优之前，不要对 scheduling
出手。

#### 附记：「卡在 96%」到底是什么意思

工厂跑完那天有一段小小的 debug 经历，值得单独写下来，因为它教的
这一课某种意义上比 Phase 4.5 的技术结果还更有用。工厂在后台跑了
一整天。傍晚我们 check in，进度计数器读出来 `11,762 / 12,259` ——
95.9%，看起来卡死了完全不动，一小时后再看还是同一个数字。第一反
应是「工厂在 96% 崩了，还有 497 条 edge 没完成，得重启调查」。

我们差点就这么干了。拦住我们的是在动手之前先看日志文件
（`tmp/nvfac.log`）。日志的最后一行干净得不能更干净：

```
== done ==  ok=11715  fail=0  jb_fail=0  elapsed=676.5min
```

工厂根本没崩 —— 它在启动后 11 小时 16 分钟正常收工了，零失败。那
「缺了 497 条」从哪来的？

它来自两个不同的分母被当成同一个数。我们一直在看的进度计数器报的
是 `len(done)` 比上 `12,259`（从 STA dump 抽出来的原始 edge 数）。
但工厂开跑前会先把 `12,259` 过滤到 `11,762`，剔掉双 LUT 模板 place
不了的 edge —— 奇 N 自环、IO-ring 坐标、非 LAB 列。被过滤掉的 edge
根本不会进 work queue，也就不会被标记为 done，于是 `len(done)` 渐
近到的极限是 `11,762`，不是 `12,259`。一旦工厂跑到 `11,762 / 12,259`，
它就是 **完成了**，不是卡住了。

教训：一条长时间运行的 pipeline 在末尾「冻住」时，在动手重启之前
先读一遍真实的日志。一个分母写错的进度计数器，看起来和一个分子卡
死的崩溃进程在 status 上长得一模一样 —— 两者都给你一个不变的数
字。区分它们只需要一条 grep 日志。重启一个已经跑完的 pipeline 往
好里说是浪费（白起 12 个 Quartus worker），往坏里说是破坏性的
（如果「修复」动了 checkpoint 文件，你可能丢掉 pipeline 已经做完的
活）。「看起来不对劲，先重启」这种反射是长时间运算里最贵的反射之
一，几乎每一次正确的第一步都是「看起来不对劲，先读日志」。

这也解释了为什么我们 README Phase 4.5 章节把覆盖率写成
「11,762 / 12,259（95.9%） —— 可 place edge 的 100%」。两个数字同时
为真：工厂做到了它能做到的一切，而这个「一切」占原始 edge 清单的
95.9%。只写 95.9% 会让结果看起来比实际差；只写 100% 又掩盖了现行
编译模板够不到的那 4.1% NEORV32 结构。两个数字都值得记下来。

---

### 那个不肯闪烁的 24-bit 计数器：缺一个 primitive，不是 codec 的 bug（2026-04-11）

这是项目至今为止学费最贵的一课。值得用大学课本的语气讲一遍，因为
同样的坑会捧着每一条把老牌 vendor 芯片硬接到 generic place-and-route
引擎上的开源 FPGA 工具链摔一遍。

**起点。** Phase 5.3 终于把整条开源流程拼齐了：Yosys 把 Verilog 综合成
LUT4 + DFF；nextpnr-generic 用我们手写的 `chipdb_gen.py` 把 cell 摆到
EP4CE6 上；`np2fasm.py` 走一遍布线后的 JSON，把每个 LE 和每条弧变成
FASM 指令；`fasm2rbf.py` 吃掉 FASM，对每条 route 在我们的 13,487 条
sig-cache 里查一次，写出一个 CRC 合规的 368,011 字节 `.rbf`。冒烟
测试就是我们能想到的最简单的时序设计：

```verilog
module counter_top(input CLK, output LED);
    reg [23:0] cnt;
    always @(posedge CLK) cnt <= cnt + 1;
    assign LED = cnt[23];
endmodule
```

24-bit 计数器。50 MHz 时钟下最高位每秒翻 3 次左右 —— LED 应该清楚地
肉眼可见地闪烁。整条管线 5 秒跑完：31 条 LUT 指令、24 条 DFF 指令、
97 条 ROUTE 指令，所有 CRC 帧干净，所有 LI MUX 安全检查全绿。烧。

LED 恒亮。再试，恒灭。我们换了 10 种重建方式（顺序、剥离策略各种
fix），LED 一直只在「全亮」和「全灭」两个状态里来回跳，从来不闪。

**那一段红鲱鱼。** 每次烧完看到 LED 不动，我们都假设 codec *快*对了，
再来一个小修就能跑。我们真的修出 —— 而且确实是真 bug —— `fasm2rbf.py`
和 sig-cache 的五个错误：

1. `LutCodec` 用「所有 minterm pattern 的并集」算一个 LUT 占了哪些
   CRAM cell。这在 LAB 稀疏占用（一两个 LE 在用）时是对的。但 counter
   要在两个相邻 LAB 里塞 30 个 LE，每个 LE 校准里 50+ 个 LAB-shared
   bit 就开始互相污染。Workaround：用 `predict_sram(0xFFFF)` —— 它
   会 XOR 抵消每一个出现在偶数个 minterm pattern 里的 cell，正好剩
   每个 LE 的 16 个真实 truth-table cell。

2. (X=4, Y=18) 和 (X=4, Y=19) 这两个 LAB 内部少了 160 条 sig-cache
   条目。我们用一个干净的 two-LUT pair 模板重挖了一遍，得到漂亮的
   每条 135 cell 的结果。

3. 早些 session 里出现的「self-loop 挖掘模板」其实在挖错的 port ——
   它的 Verilog 把一个 flip-flop 塞在两个 LUT *中间*，并且把
   `lut2.dataa(reg)` 写死了，不管调用方要的是哪个 port。它产出的
   160 条条目都是废的。（我们扔掉重挖。）

4. Per-LAB 的时钟分发 cell，在两个特殊位置上正好和某个 LE（X4Y19N4）
   的 truth-table cell 重叠。我们的 build 在重置 LUT 区域的时候顺手
   把时钟 cell 也清掉了。Fix：把 per-LAB CLK 的 SET 移到 LUT phase
   *之后*，而不是之前。

5. sig-cache 挖掘的 baseline 是 `nv_zero_global.rbf`，它本身在
   (X10Y10/X10Y11) 上含一个 lut1+lut2 的小桩。基于它挖出来的 route
   会漏 1-3 个 LI MUX cell 在那两个 baseline LAB 里。Fix：bitgen
   之后再走一遍 LI 结构，把任何不在 design LAB 的 cell 翻回 baseline
   状态。

每一个修复都是真的。**没有一个是真正的问题。** 把五个修都打上之后，
LED 还是不动。

**我们应该在 Day 1 跑的那个 30 秒测试。** 终于，气得我们做了一件
显然该做的事：把上面这份 Verilog 直接喂给 Quartus，把 Quartus 出来
的东西烧上去。Quartus 出来的也是一份 368,011 字节的 `.rbf`，跟我们
的一样大。烧。

它闪了。3 Hz 左右，肉眼可见，正如预期。

所以矽片好的。时钟好的。pin map（CLK 接 E1，LED 接 G15）对的。
`openFPGALoader` 对的。板子对的。Verilog 对的。**唯一不对的是我们
的比特流。**

这意味着我们现在能比较两个对应同一份 Verilog 的 `.rbf`：我们的和
Quartus 的。各自和空 baseline `nv_zero_global.rbf` 做差，数 cell：

```
Quartus reference（会闪）：    367 cells，主要在 CRAM 第 47-48 列
我们 codec build（不动）：  1,185 cells，主要在 CRAM 第  4-7 列
两者重合的 cell：               55
```

两份 build 几乎完全不相交。它们不是在同一块芯片区域里抢 cell ——
它们把这个设计放到了**完全不同的物理位置**，用着**完全不同的 LE
原语**。

**真正的根因。** Cyclone IV 的 LE 之间有一种特殊的直连线叫做
「进位链」：每个 LE 的 `cout` 输出直接走进下一个 LE 的 `cin` 输入，
是一根专用的硬连线，**根本不经过 local interconnect MUX**。硬件
加法器靠它把进位以「一根线」的速度传上去，而不是「一次布线决策」
的速度。

Quartus 看到 `cnt + 1`，识别出这是算术操作，就把 LE 切到「算术
模式」，把 24 个 LE 在一列里串起来，`cout → cin` 全是直连线。
**每个 counter bit 一个 LE**，进位信号完全不经过 LI MUX。

Yosys + nextpnr-generic 不知道这件事。我们的 `chipdb_gen.py` 声明了
LE、声明了 LI MUX 线、声明了 C4/R4/R24 路由 track，但是**没有**声明
进位链 `cout → cin` 的直连线，因为我们从来没建过这个模型。所以
Yosys 看到 `cnt + 1` 时，没有 carry primitive 能映射，就只能用它
唯一会的方式去展开加法 —— 拆成普通的 4-input LUT。一个 ripple
adder，每个输出 bit 算成类似 `A ⊕ B ⊕ Cin`，进位算成
`(A ∧ B) ∨ (Cin ∧ (A ⊕ B))`。每个 counter bit 大约要 4 个 LE 才能
表达完，所以 24-bit counter 炸成 30+ 个 LE。而且每个 bit 都要把*
自己上一拍的值*作为输入 —— 也就是一根从 LE 的 flip-flop 输出回到
它自己 LUT 的某个输入 port 的线。**一个 self-loop**。

这就是我们工具链怎么修都修不过去的那堵墙。sig-cache 挖掘模板的
基本假设是「在两个不同位置各放一个 LUT，把得到的 bitstream 跟空
baseline 做 diff」。它没法表达 self-loop —— 你不可能把两个不同的
LUT 摆在*同一个* LE 坐标上。我们试过另一个模板：把同一个 LUT 在
「外部输入」和「self-feedback 输入」之间换一下；但两次 compile
之间 Quartus 想换 I/O pin 就换、想重新布线就重新布线，diff 出来
的「self-loop entry」是 100-700 cell 的随机噪音，不是我们要的
那一小撮 LI MUX bit。

没有干净的 self-loop sig-cache 条目，设计需要的 24 条 self-feedback
路由就没有信号传过去。每个 counter bit 的 flip-flop 看到的就是
一个常数输入。flip-flop 锁住开机时的初始值不再变。LED 永远停在
bit 23 上电后的状态 —— 一种 build 下是 1，另一种 build 下是 0。

**教训，三句话写完。**

> 当一条开源工具链产出一个「应该」能跑但不跑的 bitstream 时，
> **一定要先用 vendor 自己编译同一份 Verilog 当 ground truth，
> 再去动 codec。** 30 秒在 Quartus 里编一遍测试设计、烧一次、做
> 一次 byte diff，立刻就能告诉你：你是在追一个 codec bug（cell 列
> 对的、值不对），还是在追一个 missing primitive bug（cell 完全
> 在另一列，因为前端发出来的是一种完全不同的拓扑）。这两种情形
> 需要的修复完全不同，混为一谈会白白浪费掉一大段时间。

**给学生读者的话** —— 底下还有一个更细的教训。一颗现代 FPGA
不是「一片 LUT 海加一张布线网」。它是一组**故意做成异质的**原语
集合：LUT、FF、进位链、BRAM、DSP 乘法器、PLL、IOB、GCLK 树。vendor
的工具知道这每一种原语的存在，并把它们当作一等公民。一条 generic
place-and-route 工具只能看到你 chipdb 告诉它的东西。**任何你
忘了塞进 chipdb 的原语，vendor 都会在 cell count 上以 3-10× 的
优势、在性能上以无穷倍的优势悄悄把你压在地上。** 这就是这个项目
下一个阶段（Phase 5.4）的全部意义所在：教 chipdb 认识进位链，让
`cnt + 1` 重新变回 24 个 LE 一列，回到它物理上本来的样子。

这也是为什么开源 FPGA 工具链历史上最先做的都是最小最简单的器件。
iCE40 几乎没有异质原语 —— 主要就是 LUT、FF、BRAM —— 所以
Project IceStorm 才能最先落地一条完整的开源流程。Cyclone IV 比它
丰富一两代（有进位链、有 DSP 乘法器、有 M9K BRAM、有 PLL、有软
I/O 标准），每一种丰富出来的特性都是一道悬崖，generic 流程在没
有人去教 chipdb 认识它之前就会从那里摔下去。好消息是每道悬崖
只需要爬一次：一旦 chipdb 里有了 carry primitive，*所有*以后做
算术的设计都白嫖到了。

这次乱追过程里赚到的修复，对未来任何「在一个 LAB 里塞很多 LE」
的设计都仍然有用 —— LutCodec workaround、干净重挖的 inter-LE
配对条目、per-LAB clock 顺序规则、bitgen 后 LI 清理。它们没救
得了 counter，但合在一起构成一个高密度组合逻辑和 FF-only 设计
的可工作模板（`tmp/m5_counter/build_counter_sigcache.py`）。
Phase 5.4 会把进位链变成我们爬的下一道悬崖。


### Phase 5.4 后续：那道悬崖，已经爬上来了（2026-04-13 → 04-14）

上面那段 counter 破案故事停在悬崖边。这一段是爬上来的过程，特地
写给学生读者，尽量讲具体。

**算术位到底在哪里。** Phase 2.4 当年声称在每个 LE 的 CRAM 区里
挖到了「92 bit 的纯算术/进位链位」。那个结论**是错的** —— 它是
用 `VIRTUAL_PIN` 编译挖到的，而 Phase 5.0 后来在 M9K/DSP 工作里
发现，`VIRTUAL_PIN` 会让 Quartus 吐一大堆幽灵布线 cell，换成实物
pin 再编一次就消失。我们换成实物 pin 重挖，每 LE 的「算术位」全
部消失了 —— 它们根本就没存在过。

真正存在的是：算术模式是个 **LAB 级的模式开关**，不是 per-LE
设置。一旦 LAB (X, Y) 里**任何一个** LE 开了算术模式，大约 100
个 bit 会在 **block band**（frames 1692-1738）里点亮 —— 就是那块
用来启用 M9K RAM 块和 DSP 乘法器的带子。**不存在 per-LE 的算术
CRAM cell**。心里的模型是这样的：一个 LAB 里 16 个 LE 共用同一
份算术模式配置，所以配置位是按 LAB 存一份，不是 16 份。这和 CPU
的做法一模一样 —— 你不会给每对寄存器都配一个 ALU，你只有一个
ALU 加一个 mode 字段。

**这份 blob 在所有 LAB 上位置无关。** 挖到 LAB (4,18) 的 ~100 个
cell 后，我们问：LAB (10,18) 是不是用另外 100 个？LAB (4,10)
呢？「三角测试」（2026-04-14）在这三个 LAB 各做一次 8 位 counter，
每个都跟自己的 identity 双胞胎做 diff。三份 diff 产生的 cell 集
**逐字节相同** —— 不管把 counter 放在哪个 LAB，block band 里亮
起来的都是同样那 100 个 offset。我们把它叫 **v4 universal blob**
（100 个 SET + 4 个 CLEAR），落盘成
`results/arith_blockband_v4.json`。FASM codec 学一张表，全片通用。

**这份 blob 按 WIDTH 分类，不按 N-slot 分类。** 16 位 counter 需
要 197 个 block-band cell，不是 100 个；24 位跨两个 LAB 的 counter
需要 295 个。所以 blob 跟进位链有多长是相关的 —— 但它是不是也跟
你用了 LAB 里**哪几个** N-slot 相关呢？Cyclone IV 的一个 LAB 有
16 个 LE，分别在 N=0, 2, 4, …, 30 的槽位；把其中 8 个放在下半
（N=0..14）和放在上半（N=16..30）是两种物理上完全不同的摆法。

Phase 1 全面扫荡（2026-04-14，42 次 Quartus build，不需要硬件）：
对每个 `w ∈ {2, 3, …, 16}`，在 LAB (4,18) 各做两次 `w` 位 counter
—— 一次下半（N=1..2w-1），一次上半（N=17..2w+15）。fit 报告确认
两种摆法都被尊重了。然后每个 counter 跟匹配的 identity 做 diff。
结果：**每一个 width 下，下半和上半的 diff 都是逐字节相同的** ——
一模一样的 offset，一模一样的 bit 位置。把同样 8 个 LE 搬到同一个
LAB 的另一半，CRAM 里的算术 bit **一个都不变**。我们本来害怕要
挖 `2^16` 种 N-slot 组合，结果只需要**按 width 做一张表**（一个
chain 长度一个条目）就够用了。那张表现在在
`results/arith_blockband_by_width.json`，覆盖单 LAB width 2..16
加一个 16+8 跨 LAB 组合；往返验证（blob 贴到 identity 上，跟
counter 做 diff）每一条都是 0 data diff + 0 block-band diff。

**路上顺便拆穿两个迷思。**

*迷思 1 —— 「每个 LE 有一个 FF-enable CRAM 位」。* 我们用三种方法
挖那一位，每次挖回来都是噪声。拿 Quartus 做对照：Cyclone IV 的
每个 LE 都有一个**永远物理存在**的 flip-flop。你到底是**用**
flip-flop 还是**用**组合输出，是由下游布线决定的，**不是由 CRAM
位决定的**。之前那份 `dff_cells_mined.json` 其实是布线基础设施
的噪声。FASM `DFF` 指令现在变成 parse 出来就丢弃的 no-op。

*迷思 2 —— 「进位链需要外部反馈布线」。* `N` 位 counter 是
`Q <= Q + 1`，所以每个 FF 的 `Q` 要回到 ALU 的 B 输入。我们最早
的 Yosys techmap 加了一个「Route-A buffer」LUT，把反馈信号走
local interconnect 送回去。这么做 LE 数量翻倍，而且制造出 24 条
sig-cache 无法干净挖掘的 self-feedback 路由。后来我们扒 Quartus
自己编的 counter：**反馈路径上零条外部布线 cell**。Cyclone IV 的
LE 内部有一条直通线，从 FF 输出直接接到 ALU 的 B 输入，**根本不
经过 LI MUX**。`synth/ep4ce6_map.v` 的修法是：让 FF 的 `Q` 直接
连到 `CE6_CARRY.B`，中间不插任何 buffer。现在 8 位 counter 用 8
个 LE + 0 条 route cell，跟 Quartus 一致。

**硬件上跑到哪一步了。** 2026-04-13 那天，我们把一颗完全用 FASM
组装的 8 位 counter（identity 基底 + 8 条 `LUT_ARITH = 0x0000`）
烧进 AX301。LED 以预期频率闪烁，行为跟 Quartus 自己编同一份
Verilog **逐 bit 相同**。identity `Q <= Q` 的阴性对照组产生熄灭
的 LED。这就是完整证据：block-band arith blob 就是真的算术激活、
universal blob 在目标 LAB 上成立、LE 内部反馈够用（不需要外部布
线）、FASM `LUT_ARITH` 指令端到端正确接通。Width 9..16 和 24 位
跨 LAB 的情况，diff 跟 Quartus 输出逐字节相同，但硬件复验要等
板子下次回到桌面再做。

**一句话结论。** 进位链不是我们原本猜的「每个 LE 一套另外的 cell」，
而是**一个 LAB 级的模式开关**，存在跟 M9K、DSP 启用共用的 block
band 里，bit 模式只跟进位链**多长**相关，跟 LAB 里**是哪几个** LE
参与无关。


---

## 开源工具链端到端：原生路径 + ζ 逃生通道

从开源 bitstream codec 通向 silicon 目前有两条路 —— **原生路径**
（Yosys → nextpnr → FASM）和**逃生通道**（拿 Quartus 产出的 RBF、
跟 baseline 差分、emit 纯 `BIT` 指令）。两条路最终都走 `fuzz/fasm2rbf.py`
产出可烧的 bitstream。原生路径是长期目标；逃生通道是只要 Quartus
能编的设计就一定跑得通的 fallback。

### 原生路径

```text
.v / .vhd
   │
   ├── Yosys techmap (synth/ep4ce6_map.v, synth/prims.v)
   │     → LUT4, DFF, CE6_CARRY, EP4CE6_M9K, GENERIC_IOB
   │
   ├── nextpnr-generic (chipdb 来自 fuzz/chipdb_gen.py)
   │     → placed + routed JSON
   │
   ├── synth/np2fasm.py
   │     → FASM (LUT, ROUTE, LUT_ARITH, M9K_MODE, IOB_*, GCLK_PIN,
   │            LAB_CLK_SEL, LAB_CLK_SEL_LE, OUTROUTE_G15, IOB_PAD_NV)
   │
   ├── fuzz/fasm2rbf.py  (+ patch_rbf_crc)
   │     → .rbf（368 011 B，CRC 已修补）
   │
   └── openFPGALoader -c usb-blaster
```

原生路径上硬件验证过的设计：带 DFF 的 AND gate（KEY2&KEY3→DFF→LED0）
在 LAB(16,4)、5-bit carry counter、M9K smoke 9×512 RAM、F17 上
全部 12 个可用时钟 pin 的 clock-pin pipeline。

### ζ 逃生通道（Quartus gold → BIT FASM）

对于密度太大、当前 chipdb 路由模型搞不定的设计（NEORV32 级，~6000+ LE），
`scripts/bit_workaround/quartus_gold_to_bit_fasm.py` 提供一个**可靠的**
绕行方案：

```text
design.v / .vhd
   │
   ├── Quartus 编译 → design.rbf (gold)
   │
   ├── scripts/bit_workaround/quartus_gold_to_bit_fasm.py
   │     → 纯 BIT 指令的 FASM（每个跟
   │       results/rbf/nv_zero_global.rbf baseline 不同的 bit 发一条）
   │
   ├── fuzz/fasm2rbf.py  (+ patch_rbf_crc)
   │     → .rbf（跟 Quartus gold byte-identical，cmp 证实）
   │
   └── openFPGALoader -c usb-blaster
```

这条路的价值在于：
1. 它**证明** codec round-trip 在 SoC 级别正确 —— 重建出来的 RBF
   就是 Quartus 原本产出的那些字节。
2. 它是真正的逃生通道。碰到 chipdb 路由墙的用户有一个有界的工作流：
   Quartus 编一次，下游全部还是开源工具链。
3. BIT FASM 是**可审计的中间层** —— 可以逐行对照 codec 的 CRAM
   几何模型，也可以作为 bitstream mutation 实验的底座（见下文
   「长期方向」）。

硬件验证：两 LAB cross-LAB AND→DFF 路由重建（2026-04-22）、
lits_pair route-family 重建（2026-04-23），以及完整的 **NEORV32
bootloader**（4712 LE / 2367 DFF / 19 M9K）在 AX301 silicon 上以
19200-8N1 UART 正常启动（2026-04-23）。ζ + fasm2rbf 总耗时约
0.5 秒，跟设计密度无关 —— 只跟 RBF 大小（固定 368 011 B）成正比，
不是 LE 数。

**Linux 延伸测试（2026-04-24）**：`boot_linux.py --rbf` 用 ζ 重建
的 RBF 走完 Quartus-flow 完整 host 流程 —— stage2 upload、baud
switch、kernel xmodem（1.5 MB，CRC 对）、DTB + initramfs 都对；
**Linux 6.6.83 在 RISC-V 上跑了 ~150 秒**（devtmpfs mounted、
ttyNEO0 console、exec'd /sbin/init），然后 kernel panic 在
`kernel/cred.c:103`。这个 panic 不是 ζ 的问题 —— RBF SHA256 跟
Quartus gold 一致，是 kernel 层的 RISC-V nommu 边角情况。ζ 验证
目标（「开源工具链能产出 silicon-functional NEORV32 bitstream」）
达成。

### ζ 产线化管线（CI 友好）

三步 ζ 转换（Quartus → BIT FASM → 重建 RBF → 烧写 → UART 验证）
被包成一条命令，带机器可读的 gate：
`scripts/bit_workaround/zeta_pipeline.py`

```bash
# RBF 输入，只做 round-trip + byte-identity（不动硬件）：
python3 scripts/bit_workaround/zeta_pipeline.py gold.rbf

# Quartus 工程输入（先跑 map/fit/asm/cpf）：
python3 scripts/bit_workaround/zeta_pipeline.py path/to/design.qpf

# 端到端含板子：
python3 scripts/bit_workaround/zeta_pipeline.py gold.rbf \
    --flash --uart-seconds 10 --baud 19200 --expect "NEORV32"
```

只有所有 requested gate 全过才 exit 0；`--json` 输出机器可读报告。
pipeline 在 fasm2rbf 之后硬 gate `cmp -s rebuilt gold` —— 下游 codec
任何回归会立刻暴露，不会白烧一轮 flash。

配套工具：

- `scripts/bit_workaround/zeta_rbf_diff.py A.rbf B.rbf` —— region-aware
  的 diff，把 368 011 B RBF 切成 preamble / header-data /
  header-crc / fabric-data / fabric-crc / postamble 六区，输出
  per-region byte/bit 差异 + frame histogram。避开「任一 data bit
  翻动 → CRC 连锁 → raw cmp 根本看不懂」的老痛点。
- `scripts/bit_workaround/zeta_selftest.py` —— 亚秒级 CI 风格 smoke
  test，跑三条无硬件 gate 对 HW-validated 的 `two_lab.rbf` gold
  （1710-bit 不变量）。适合当 pre-commit hook，ζ → fasm2rbf →
  byte-identity 整条链全绿才 exit 0。
- `scripts/bit_workaround/zeta_regression.py` —— 语料库级回归：遍历
  `tests/zeta_corpus/manifest.json` 里每个 fixture（由 SHA256 +
  per-region cell counts 双重锚定），验证字节级往返 + region footprint
  双重不变。selftest 抓不到的漂移（比如只影响单-LAB fixture 的 ζ
  改动）这里会 fail loud。`--reanchor` 仅更新 `TBD` 条目；
  `--reanchor-all` 接受当前值为新锚点（仅在有意改动时用）。
- `scripts/bit_workaround/zeta_manifest_diff.py A.manifest.json B.manifest.json` ——
  两个 pipeline manifest 的差分，完全不碰 RBF 本体。`zeta_pipeline.py`
  每次成功后会在重建 RBF 旁边写一份 sidecar manifest（gold/rebuilt/base
  的 SHA256、region cell counts、git HEAD、时间戳、所有 gate），
  所以 bootloader v1↔v2 对比变成两份小 JSON 的 diff，不必重扫 bitstream。
  同时能把高危场景（gold 相同但 rebuilt 不同 → ζ 或 fasm2rbf 漂移）
  标成 HIGH severity。

### pre-commit hook（按 clone 选择开启）

`.githooks/pre-commit` 在每次 commit 之前跑 `zeta_selftest.py`。按
clone 开启：

```bash
git config core.hooksPath .githooks
# 临时跳过一次：ZETA_SKIP=1 git commit ...
```

Hook 对 gitignored fixture 有防御：如果本地没有 two-LAB gold，它会
带 rebuild 提示直接跳过，不因此挡住 commit。

### `--rebuild-check`（Quartus 决定性闸）

ζ 隐含假设「同 Verilog → 同 gold RBF」。`.qpf` 输入时加
`--rebuild-check` 会把 `quartus_map/fit/asm/cpf` 再跑一遍并字节比对两份
RBF。这是在 Quartus 非决定性把下游 byte-identity 默默打穿之前唯一
廉价的检出方式：

```bash
python3 scripts/bit_workaround/zeta_pipeline.py path/to/design.qpf \
    --rebuild-check
```

### 什么时候用哪条路

| 设计规模 / 路由 | 原生路径 | ζ 逃生通道 |
|-----------------|----------|------------|
| 小（≤ 50 LE）、单 LAB | ✅ 首选 |（多余）|
| 中（50–500 LE）、跨 LAB | ✅ 如果 sig-cache 覆盖了路由 | ✅ fallback |
| 密集（> 1000 LE）/ NEORV32 级 | ❌ chipdb 路由模型过不去 | ✅ 首选 |
| Carry chain、M9K、clock pin | ✅ 硬件验证过的 primitive | ✅ 天然有效 |

原生路径仍是前沿 —— chipdb 路由模型是「不用 Quartus、从 Verilog
到 silicon」这条路上唯一剩下的 blocker。ζ 在此之前把实用层面的
缺口堵住了。


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

- [x] Phase 4.5：**Plan D' sig-cache —— NEORV32 覆盖率（2026-04-09）** —— 12-worker 并行工厂（`fuzz/plan_d_prime_factory.py`）从 NEORV32 STA edge 编译 11,715 对位置锁定的 2-LUT 对。7-tuple sig-cache `results/route_cells_full.json` = **13,487 条目**（legacy 1725 提升至 sn=0 + 工厂 11,762）。覆盖率：**NEORV32 edge 的 95.9%**（可 place 的 100%）。英雄测试 X=5 越狱列 FASM → AX301 矽片验收通过。
- [x] Phase 5.0：**非 LAB 块（DSPMULT + M9K）—— 实物 pin 重挖（2026-04-08）** —— 详见上方「进行中」章节
- [x] Phase 5.2：**M9K init 内容编解码器 —— Stage A+B 闭合（2026-04-09）** —— 三带分区（data/mode/clock）；2D 线性公式 `byte(w,bit) = anchor + (w//2)*210 - (w%2) - 2*bit, bp=6`；31 个 NEORV32 M9K 点位校准（`M9K_INIT_ANCHORS` = 33 条目）；LOC 修复（用实例名 `-to "u"`）；READ 512/512，WRITE 与 Quartus 0 CRAM diff。`fuzz/m9k_init_basis.py`

### 未来工作

- [ ] Phase 5.1：完善布线编解码器覆盖率（目标：所有线类型 >90%；C16 + 剩余 R4 I-index 仍未结）—— 与已完成的 Phase 5.0 非 LAB 工作不同
- [ ] Phase 5.2b：非 LAB 块参数解码（CLOCK_ENABLE 和 M9K INIT 之外）—— 需要「块内差分探针」绕过 header 噪声地板、STA 黑盒、以及每点位配置不可观察这三堵墙；PLL 探针（用 `PLL_1`/`PLL_2` 单例 LOC）延到这里做
- [~] Phase 5.3：**开源工具链 —— Yosys + nextpnr-generic + FASM（部分开通）**。目标：用 `Verilog → Yosys → nextpnr-generic → np2fasm → fasm2rbf → openFPGALoader` 取代 Quartus。当前状态：
  - `fuzz/chipdb_gen.py`：生成 nextpnr-generic Python chipdb（8,241 bel、59,611 wire、138 万 pip），含 GCLK broadcast、LAB 内直连 pip、4 级 pip 代价阶梯（SIG=1 < INTRA=2 < LOCAL=5 < HOP=20）
  - `synth/ep4ce6_map.v` + `synth/prims.v` + `synth/synth_ep4ce6.ys`：Yosys techmap 链（LUT4 + DFF + `$alu` 走 CE6_CARRY）。通过 `synth/synth_ep4ce6.sh` 调用 —— 包装脚本会 envsubst 展开 `$HOME` / `$NEORV32_ROOT`，VHDL 路径跟着仓库走
  - `synth/np2fasm.py`：从 nextpnr 布线 JSON 提取逻辑连通性，查 sig-cache 生成 FASM ROUTE 指令，并走进位链发射 `LUT_ARITH` 指令
  - `fuzz/fasm2rbf.py` 已端到端跑通的指令：`LUT`、`ROUTE`（6/7-tuple）、`GCLK`、`DFF`（parse 出来即 no-op —— FF 是矽片默认）、`BIT`、`SRC`、`LUT_ARITH`、`M9K.INIT_{w}x{d}`（33 个已校准的 9x512 anchor；FASM round-trip 测试 `fuzz/test_m9k_init_directive.py` 5/5 通过）。CRC patcher 已整合。np2fasm 的 M9K 发射仍是 stub（`_emit_m9k_init` + xfail 测试 `fuzz/test_np2fasm_m9k.py`）—— Yosys `$__M9K_SP_` techmap 规则草稿放在 `synth/ep4ce6_map.v`，用 `M9K_TECHMAP` ifdef 守门；chipdb 的 M9K wire pip 仍待补
  - **M5 counter —— 8 位 counter 已经可以经开源流程在硬件上闪烁（2026-04-13）。** FASM 路径（identity 基底 + 8 条 `LUT_ARITH = 0x0000`）在 AX301 上烧出跟 Quartus 自己编的 counter 逐 bit 一致的行为。Width 2..16 单 LAB 以及 16+8 跨 LAB 的情况，diff 跟 Quartus 输出逐字节相同，硬件复验待板子回到桌面再做。详见上方「Phase 5.4 后续」叙事章节
  - **追 M5 过程中赚到的真实修复（对未来 multi-LE-per-LAB 设计仍然有用）**：LutCodec 高密度 LAB workaround（`predict_sram(0xFFFF)` 过滤掉 LAB-shared 干扰）；sig-cache 挖掘模板坑已写入文档（必须用 `verilog_gen.py` 的 `gen_two_luts_single_input_clocked`）；160 个干净重挖的 (4,18)/(4,19) inter-LE 配对条目并入 `route_cells_full.json`；per-LAB CLK 顺序修复（必须在 LUT phase 重置之后再 set）；bitgen 后的 LI 清理（去掉 sig-cache 挖掘的 baseline LAB infrastructure 漏出来的 cell）。可用的 multi-LE-per-LAB build 模板：`tmp/m5_counter/build_counter_sigcache.py`
  - **IOB FASM cell map 已落地（2026-04-14）**：`IOB_IN PIN_X` / `IOB_OUT PIN_X` 指令以 `iob_in_E15.rbf` 为基底做 XOR delta，44/44 条单轴 ground truth RBF 逐 bit 一致。`np2fasm` 为每个 placed GENERIC_IOB 发一条指令。跨轴引脚组合还漏 ~57 byte 的 joint-placement 信息（需要 2D K×LED 扫频补齐）
  - **GCLK 管线已落地 + 硬件验证（2026-04-14）**：`GCLK_PIN` + `LAB_CLK_SEL` + `LAB_CLK_SEL_LE` FASM 指令在 AUTO baseline 上叠加 XOR delta。源编码 per-pin（E1=3 cells、R8=5、N1=38；legacy E1/R8/N1 三元组之间零重叠）。26 个 (LAB, N) 组合 round-trip bit-perfect；`fasm2rbf` 11/11 + `np2fasm` 7/7 测试通过。下一波硬件烧录后可以正式退役 `nv_zero_global.rbf` 基底
  - **GCLK + IOB_CLK_INPUT 扩展到 F17 全部专用时钟引脚（2026-04-15）**：`GCLK_PIN` 和 `IOB_CLK_INPUT` 现在各覆盖 **12 个时钟引脚** —— 原有 E1、R8、N1 之外新增 9 个专用时钟引脚（M1、M2、T4、R4、M16、M15、E15、A14、B14）。F17 13 条专用时钟引脚里有两条无法 fit：PIN_E2（E1 的 LVDSCLK_00P 差分对侧 —— Quartus 拒绝单端摆放）以及 PIN_H1（被 `ALTERA_DCLK` JTAG 配置脚保留）。挖矿工具已通用化：`scripts/iob_slice_mining/compute_clk_pin_hdr.py --build --pin {PIN}`（IOB_CLK_INPUT，可并行，约 16 s/pin）和 `fuzz/clk_pin_autoforce_probe.py --pin {PIN}`（GCLK_PIN，每个 pin 6 次 build × 约 16 s）。测试：`fuzz/test_iob_baseline_nv_directive.py` 15/15（包含每条引脚的 loader + 每条引脚的 gold-RBF round-trip）+ `fuzz/test_gclk_pin_directive.py` 11/11（每条引脚 loader 健壮性）。注意点：同 bank 的专用时钟引脚（E15/M15/M16；A14/B14）会共享 spine cell（重叠 12-22 cells），不像 legacy 三元组那样彼此互斥 —— XOR 语义在双重发射时仍然正确合成，但同时发射多条 `GCLK_PIN` 的设计会出现部分对消而非干净并集
  - **IOB→SLICE 路由挖掘，模板硬件验证通过（2026-04-14）**：`scripts/iob_slice_mining/` —— 成对双 LE 挖掘模板（`template_pairs.py` + `mine_iob_routes.py`）产出 pair-vs-zero 差分（每条 ~200 cells），同时 paired RBF 本身就是一个能跑的矽片设计：`iob_pair_E16_10_4_0_dataa.rbf` 烧到 AX301 上，KEY2→LED0 行为正确。3 层分解（`decompose_deltas.py`）把每条原始 delta 拆成 universal_infra（98 cells）∪ pin_footprint(pin) ∪ pure_common(target) ∪ ≤2-cell 残差，15 条（E16/E15/M16 × 5 目标 LAB）全部闭合。Port MUX 被 Quartus 规范化（4 个 port 产生逐 byte 相同的 delta）。Sig-cache 注入仍未完成（`pure_common` 是相对 `iob_zero` 基底的，不是 `nv_zero_global`）
  - **IOB_ROUTE FASM 指令 + 帧分裂桥接 + single_le 扫频（2026-04-15）**：`IOB_ROUTE PIN_X -> XaYbNc.port` 已接入 `fasm2rbf`（8/8 测试），`absolute_cells` 路径 CRAM 带逐 byte 与硬件验证过的 pair RBF 对齐。`IOB_BASELINE_NV`（`nv_zero_global` → `iob_in_E15` 的 132-bit-cell / 74 byte header 桥接 delta）与 `IOB_CLK_INPUT PIN_{E1,R8,N1}`（专用时钟 bank pin 激活 delta，每条 40 / 64 / 70 cell，通过 `scripts/iob_slice_mining/compute_clk_pin_hdr.py --build --pin {PIN}` 按 pin 挖掘）一起把帧分裂补齐，让端到端 FASM 设计可以直接在 `nv_zero_global` 单一基底上构建。`results/iob_to_slice_sigcache.json` 新增 opt-in 的 `single_le_cells` 段，存在时 `fasm2rbf` 会优先使用它，剥离配对模板副 LE 装饰用于单 LE 设计；系数由 `IOB_ROUTE_primary = gold_delta ^ (其他所有指令)` 对 Quartus gold RBF 求解得来。`scripts/iob_slice_mining/sweep_single_le.py` 把这套推导并行扫到所有已支持的 (pin, target) 组合：**15/15 条全部落地**（3 pins E16/E15/M16 × 5 targets 10,4,0 / 10,4,2 / 10,4,4 / 10,10,0 / 16,4,0），每条经完整 8 指令栈跑出的 RBF 都与 Quartus gold 逐 byte 一致。最后 6 条靠两个探针基础设施修复解锁：`clk_lab_sel_probe.py` 在 `target_lab` 撞到默认 SRC LAB 时自动改用 `SRC_ALT=(22,10,0)`（原先会在 `LCCOMB_X10_Y10_N0` 撞 placement），并且 `N_SLOTS` 扩到含 N=2，`LAB_CLK_SEL_LE X{x}Y{y}N2` 也可用了。测试：`fuzz/test_iob_baseline_nv_directive.py` 13/13（覆盖 E1、R8、N1 三个 clock-input pin，每一条都按 pin 单独 round-trip 到 Quartus gold 逐 byte 一致）+ `fuzz/test_iob_route_directive.py` 8/8
  - **Stage 0 硬件烧录（2026-04-16）**：24 个 RBF 烧入 AX301 —— **23 通过、1 失败**（DSPMULT_GLOBAL_ON 在矽片上被证伪）。关键结论：`NV_BASELINE_PACK` 矽片等价于 nv_zero_global（Phase 7 退役解锁）；14/14 IOB_ROUTE 配对条目矽片正确；7 条新 GCLK_PIN 时钟引脚编程验证（M15 全通过、M1/M2/T4/R4/A14/B14 编程正常）；M9K smoke 设计被芯片接受（codec pipeline 矽片干净）；DSPMULT 23 cell 集在矽片上漏电 → 开启二分法路线图。
  - **Stage 0 第二轮烧录（2026-04-17）**：M9K_MODE `_inferred_goldintersect` **通过** —— np2fasm 对所有 w=9 站点解除门控。IOB_OE PIN_R5 **失败**（LED 常亮）—— 二分法定位到 2 个漏电 cell `(363236,2)+(363672,2)`，清洗后 38 cell 集通过，loader 自动屏蔽。LUT_ARITH_MULTI_LAB WIDTH=17 **失败**（LED 常灭）—— 多 LAB 进位链保持门控。DSPMULT_GLOBAL_ON 四层二分（23→12→6→3→1）：漏电 cell = `(363236, 2)` 在 frame 1729；清洗后 22 cell 集通过。
  - **LAB_CLK_SEL_LE 扩展到 N=6/8 覆盖全部 14 个 LAB（2026-04-16）**：`N_SLOTS` 扩展至 `(0, 2, 4, 6, 8)`。56 次新 Quartus build。LAB(10,16) invariant 收紧 53→49（4 cell 迁移到 per-LE 桶）。`clk_lab_sel_per_le.py` 重构为 N 无关。49/49 测试通过。
  - **IOB_IN_BIDIR / IOB_OUT_BIDIR 指令落地（2026-04-17）**：`per_pin_input`/`per_pin_output` cell 分发，用于双向 IOB pad（cell 在 33 pin 扫频中按 pin 唯一，无 anchor 双翻转）。覆盖 16 个 sdram_dq pin。`_IOB_BIDIR_FALSIFIED` 每 pin 屏蔽表（R5 OUT：2 个 fabric 带 cell 被剥离）。np2fasm 自动为双向 pad 发射 BIDIR 变体。测试：5/5 指令 + 6/6 np2fasm。
  - **IOB_OE FASM 指令落地（2026-04-16）**：`IOB_OE PIN_X` 覆盖 16 个 NEORV32 sdram_dq pin。Specimen-factory 挖掘（oe_on vs oe_off 每 pin、3-seed routing-invariance 探针、全 16 pin 零漂移）。每 pin 37..55 cell、21 cell universal 交集。R5 硬件二分隔离 2 个漏电 cell；loader 自动屏蔽。9/9 测试。np2fasm 发射尚未接线（需 Yosys `$tribuf` techmap）。
  - **公式化 LutCodec 落地（2026-04-17）**：`LutCodec.from_cram_model(x, y, n)` 消除了 per-LAB 的 SQLite 校准。使用 CRAM 地址模型生成合成 minterm 模式。`fasm2rbf.py` bitgen 在 `from_db()` 抛 ValueError 时自动回退。在 (10,10,0) 处全部 65536 个 mask 与数据库 codec 一致。**已知缺陷**：pair mapping 对 (10,10,0) 以外的位置全部错误 —— 192/233 个 LUT 产生错误的真值表。根因：bit-to-cell pair 排列随 (x,y) 变化，公式未能捕获。这是 pipeline 测试的首要阻塞。
  - **Sig-cache 需求挖掘扩展至 38,683 条目（2026-04-18→19）**：从 NEORV32 STA edge 做路由挖掘，7-tuple sig-cache 从 13,487 扩展到 38,683 条目。NEORV32 v2 构建的路由 sig-cache miss = 0。剩余 8 条 IOB→SLICE miss（J16/M2/E16 → Y=21 目标）。
  - **M9K pipeline 端到端闭合（2026-04-16）**：完整 Yosys → `memory_libmap` → prepack_m9k → np2fasm → fasm2rbf 路径产出 CRC 合规的 RBF。smoke 设计（9×512 RAM）用户数据模式正确往返。三个 np2fasm 修复（blackbox 模块选择、Yosys 二进制整数解析、x/z 字符处理）。M9K_MODE `_inferred_goldintersect` 发射对所有 w=9 站点解除门控（硬件已验证）。
  - **NEORV32 开源工具链 RBF 烧录自动重置（2026-04-18）**：v2 和 v3 RBF 都导致 FPGA 自动重置到出厂配置。根因：chipdb LOCAL 总线仅 4 条 track（总计约 2080 wire），真实矽片有 O(100k) 路由资源。在 6500+ LE 下几乎每条 LOCAL wire 都过度使用 → 驱动冲突 → 保护性重置。所有结构安全检查通过；问题在路由模型容量，不在指令。修复需要 SIG-cache 感知放置或分层路由模型。
  - **Pipeline 测试端到端设计（134 LE，2026-04-18→19）**：28-bit counter → LED 心跳 + UART TX "Hi!\r\n" + KEY3/KEY4 直通。Quartus gold 在矽片上通过。开源工具链构建：0 route miss，但**烧录后 FPGA 重置**。根因：`from_cram_model()` pair mapping bug —— 192/233 个 LUT 使用错误的 bit-to-cell 映射，破坏 LUT 函数。K2→LED3 和 K4→LED2 工作（部分 pipeline 成功），但 F16/G15 输出失败。F16 输出路由经差分挖掘（40 个 data cell：38 header + 2 block band）已隔离，但添加它们因累积的 LUT 层损坏而触发重置。
  - **NEORV32 进位链禁用（2026-04-17）**：Yosys flow 移除 `alumacc` —— 684 条链断裂 → 改用 LUT4 算术。LE 减至 6533（少 292）。CE6_CARRY 基础设施保留供未来架构工作。

- [x] Phase 5.4：**开源流程里的 LE 进位链 —— 硬件上已验证（2026-04-13）** —— 算术模式激活住在 block band（frames 1692-1738，bp=2），**不**住在 LAB CRAM 列里；而且是 per-LAB 的模式开关，不是 per-LE 的 cell。四块拼图落地：(1) `chipdb_gen.py` 声明了 8,126 条相邻 LE bel 之间的 `cout→cin` 直连 pip；(2) `synth/ep4ce6_map.v` + `synth/prims.v` 加了 CE6_CARRY primitive，让 Yosys 把 `$alu` 落到链式 LE 上，并让 FF 的 `Q` 直接接到 `CE6_CARRY.B`（不插任何外部 "Route-A" buffer）；(3) `synth/np2fasm.py` 走进位链并发出 `LUT_ARITH` 指令；(4) `fuzz/fasm2rbf.py` 针对 8-LE 半 LAB 链直接套用 `results/arith_blockband_v4.json` 的通用 blob（位置无关，任何 LAB 都能用），其它 chain 长度则查 `results/arith_blockband_by_width.json`（widths 2..16 单 LAB + 16+8 跨 LAB）。AX301 矽片收案：identity + 8 条 `LUT_ARITH=0x0000` 烧出的 LED 行为跟 Quartus counter RBF 逐 bit 一致；identity `Q<=Q` 的阴性对照组 LED 熄灭

- [x] Phase 6：**σ⁻¹ 3-key LutCodec 突破（2026-04-21）+ 缺口补齐（2026-04-24）** —— 历史遗留的 `LutCodec.from_cram_model()` pair mapping bug 闭合。原本 `(foff, fb8)` 2-key 表在跨 Y-group 时存在歧义，新增第三维 `group = (y-2)//3` 作为 discriminator 解决。σ⁻¹ 表 `results/sigma_inv_fb8_groups.json` 在 2026-04-24 从 1,904 条扩到 **2,112 条**：Y=3 wrap 缺口 +80 条（wrap 使用 `addr_adj=206` 并含边界 N=12；Y≥6 slot=1 group 仍用 207 与严格 `<`）和 Group-4 × fb8∈{0,1,3,4} 缺口 +128 条（用替代 X 列 X=11/16/12/17 的 FACE probe；主要的窄列代表 X=3/6/4/7 撑不起 16-LUT 模板）同时落地。5 级 fallback 链保留。**残留**（无法关闭）：fb8=7 × group=4 受矽片几何约束 —— X=8 是唯一的 fb8=7 列，而它在 Y≥12 没有 LAB（Quartus 在 CE6 和 CE10 上都拒绝 `LCCOMB_X8_Y{14,16}_N*`）；这 32 个位置回退到 nearest-group（group=3 fb8=7）。

- [x] Phase 6b：**AX301 上的端到端硬件验证（2026-04-21 → 2026-04-22）** —— 三个设计经完整开源工具链在矽片上功能正确：(1) 带 DFF 的 AND gate（KEY2&KEY3→DFF→LED0）在 LAB(16,4)，10 条 FASM（含多 port IOB_ROUTE），与 Quartus gold 0 fabric diff；(2) 5-bit carry counter 在 LAB(16,4) N=0..8，18 条 FASM、0 条 ROUTE（进位反馈在 LE 内部）；(3) 两 LAB 跨 LAB 的 AND→DFF→LED，用 BIT-only 从 Quartus gold 重建 —— 跟 gold byte-perfect 且硬件验证通过。这是 codec 路径上首次在矽片验证 cross-LAB fabric route。

- [x] Phase 6c：**chipdb 26-track 升级（2026-04-22）** —— LOCAL bus 从 8 条合成 track 扩到 26 条，总 pip 数达到 3.6M；路由图更接近真实 Cyclone IV 每 LAB ~40 LI-wire 的拓扑。runner 已能驱动 P&R 端到端跑通升级后的 chipdb。小设计硬件验证通过；密集设计（NEORV32 级）路由仍然不通 —— 模型是密了，但跟真实 C4/R4/R24/LI 交换矩阵还是简化了不少。

- [x] Phase 7：**ζ BIT 逃生通道 —— 端到端在 NEORV32 上硬件验证（2026-04-23）** —— `scripts/bit_workaround/quartus_gold_to_bit_fasm.py` + `fasm2rbf.py` 把任何 Quartus 产出的 RBF 逐字节重建（相对 `nv_zero_global.rbf` baseline 每个不同的 bit 发一条 `BIT` 指令，CRC 自动修补）。NEORV32 规模硬件验证通过：4712 LE / 2367 DFF / 19 M9K / 51 pins → 127 728 条 BIT 指令（2634 hdr + 113 573 fab + 11 521 crc），ζ + fasm2rbf 总耗时约 0.5 秒。重建 RBF 在 AX301 以 19200-8N1 UART 正常启动 NEORV32 bootloader（banner + auto-boot 倒数 + SPI flash 探测 + CMD prompt）。延伸的 Linux boot 测试（2026-04-24）让 Linux 6.6.83 在 RISC-V 上跑了 ~150 秒（devtmpfs mounted、ttyNEO0 console attached、exec'd /sbin/init）后出现 `kernel/cred.c:103` panic —— 该 panic 与 ζ 无关（RBF SHA256 跟 Quartus gold 一致）。这是逃生通道首次在 SoC 级别完成硬件验证；被 chipdb 路由墙挡住的用户有了可靠的绕行方案。

- [x] **simple_led 单-LE 路径抢救 + M9K_MODE 宽度扫描 + pragma 通道（2026-04-24）** —— ζ 逃生通道落地之后的三个后续工作：
  - **Fix A（commit `8c660ef`）**：`bitgen(..., legacy_iob_route=True)` 还原 pre-6b6cda9 的 IOB_ROUTE 应用路径，供 simple_led 类单 LE 设计使用（纯 XOR parity，无 dedup，无 hdr-skip）。默认路径对配对派生 / IOB_PAD_NV 设计（two_lab、NEORV32 ζ、multi-LE）仍然正确。`simple_led` w=9/w=18 probe 现在能逐字节重建到 HW-PASS reference。
  - **Fix B（commit `af22c9f`）**：`scripts/iob_slice_mining/sweep_single_le.py` 改用 legacy 应用路径验证，新增 `--orphans-only` / `--include-known` 两个 flag；109 条 `single_le_cells`（X∈{3,4,6,7,8,10,16} × Y∈{4,10,17,18,19,21}）每条都与 Quartus gold 缓存 byte-identical。loader 优先级变成 `single_le_cells > single_le_cells_stale > absolute_cells`，所有 sigcache key 都重新可路由。
  - **M9K_MODE 宽度硬件扫描（commit `f22b884`）**：用 overlay probe 在 `cff800e` HW-PASS w=9 基线上扫描，(9,1024) 和 (36,256) 在 AX301 矽片通过；(4,2048) 失败（LED0 常亮、KEY2 无响应 —— 24-cell gi 桶被矽片拒绝），在 `np2fasm._M9K_MODE_HW_VALIDATED` 中关闭门控。硬件已验证集现在是 `{(9,512), (18,512), (9,1024), (36,256)}`。**与基线的 overlap 并不是矽片安全性的判别器**（(36,256) 0 overlap 通过；(4,2048) 0 overlap 失败）。
  - **np2fasm pragma 通道（commit `612c520`）**：`np2fasm --legacy-iob-route` / `convert(legacy_iob_route=True)` 在 FASM 顶端 prepend `# fasm2rbf: legacy_iob_route=1`。`fasm2rbf.parse_pragmas(text)` 把 pragma 还原成 kwarg dict，调用方显式 forward 给 `bitgen(**pragmas)` —— 不在 bitgen 内部做神奇的自动覆盖。6/6 测试。

### 长期方向：这个 codec 让我们能做什么，不能做什么

一个常被问到的问题：codec 已经能跑了，现代 ML（RL 路由、GNN 拥塞预测）
能不能超越 Quartus？诚实的回答分三层。

**PPA 层面赢不了。** Quartus 有 30 年的硬件校准时序模型、完整的 legality
checker，以及 PathFinder + negotiated congestion 路由算法 —— 学术界的 RL
路由器能否追上还是一个开放的研究问题。试图在 Quartus 的主场把它的路由打
趴，是一个已知的死胡同。

**这个 codec 真正独有的能力**，是对已发布比特流做 bit-level 双向修改
—— 微秒级完成一次变换，秒级在矽片上验证。Quartus 是单向的
`verilog → bitstream` 管线；我们不是。这条鸿沟带来以下 Quartus 架构上做
不到的事：

1. **比特流级 mutation 与等价性框架。** 拿一份 Quartus build，逐 cell
   做等价变换（等价 LUT mask 替换、冗余布线 bit 移除），在硬件上验证
   等价，保留能降低 cell count / 功耗的 mutation。cell-level peephole
   本身的 PPA 收益不大（Quartus 输出已经接近局部最优），真正的价值是：
   把 codec 当成 post-fit 优化与 differential equivalence testing 的
   研究基座 —— 这是 Quartus 本身无法暴露的。
2. **Quartus 不会走的工作流。** 离线的比特流 mutation 与 replay：修改
   一份已知良品 RBF 的特定 frame，下次上电直接烧回去。这**不是** partial
   reconfiguration（Cyclone IV 没有 ICAP），但它让 Quartus 单次 fit 流程
   里做不到的事成为可能 —— 例如不重跑 fit 直接打 ECO 补丁、以可重现的
   bit-identical 方式构建（Quartus 依赖随机种子；codec 是纯函数）、在无关
   紧要的 LUT bit 里做 watermarking。
3. **开源工具链（真正的奖品）。** 一条能跑通的 Yosys + nextpnr-EP4CE6 流程
   比任何 PPA 上的对比重要得多。它让 Linux/macOS 用户第一次能在不装 Intel
   工具的情况下用这颗晶片，让 CI 第一次能可重现地构建 EP4CE6 比特流，让
   **Cyclone IV E 系列**第一次进入开源 FPGA 生态（Cyclone V 已经被
   Project Mistral 先推进了一大步）。

**ML 在这里的位置**是一个适度的辅助角色：等语料够大时，用决策树分类器
替换手写的 LI envelope 规则；在 paired-vs-alternating 选择规则上用小决策
树（不是 GNN）做模式挖掘，这样结果可以直接编进 codec；对烧不上去的 codec
RBF 做异常检测。这些都不是「ML 打败 Quartus」，而是「ML 帮我们写一些我们
不想手写的规则」。

**优先级。** 把 Phase 5.3 做完。`.v → bitstream` 开源流程已经走完大部分
（chipdb + techmap + np2fasm 跑通，8 位 counter 硬件验证通过）。一旦它端
到端跑起来，问题就从「能不能在 PPA 上打败 Quartus」变成「有什么 Quartus
根本不会做的事是我们能做的」—— 回答这个问题的是 codec。

### 整体进度估算

不同领域的百分比之间没有可比性（分母各不相同 —— bit 数、cell 类型、路由
条数、设计规模）。下表以 **覆盖** 作为可核对的计数、以 **状态** 作为工程
结论（硬件验证 / 往返闭合 / 部分 / 未开始），不再汇出单一的「综合进度」。

| 领域 | 覆盖 | 状态 |
|------|------|------|
| CRAM 地址映射 | 22 列 × 18 行 × 16 LE = 376/376（CE6 白名单）+ 越狱后 X=32/33、Y=15 | 硬件验证 |
| RBF CRC | CRC-16/IBM、0x8005、init 0xFE54、frames 25..1751；1727/1727 帧通过 | 硬件验证 |
| 逻辑配置（LUT / FF / 算术） | 全部 LE 位置的 LUT TT 已解码；FF 为矽片默认（无 CRAM）；算术模式 = block-band blob | 硬件验证 |
| 开源流程的 LE 进位链 | chipdb `cout→cin` pip（8,126 条）、CE6_CARRY techmap、`LUT_ARITH` FASM 指令、widths 2..16 + 16+8 per-width 表、v4 位置无关 blob | 硬件验证（8-bit counter，2026-04-13） |
| FASM 工具链（Phase 4） | `fasm2rbf` + `rbf2fasm` + 集合覆盖分解器；1725/1725 + 41/42 + 3/3 + CE6 686/686 round-trip | 硬件验证（AND(K1,K2) on AX301） |
| 硬件回环（codec → 烧录 → 矽片） | LutCodec + FASM 路径都在 AX301 上跑通 | 硬件验证 |
| C4 布线开关 | I=0 闭式公式；I≠0 44 条逐 (X,I) 查表 + sig-cache 覆盖 | 闭式部分 + sig-cache 生产可用 |
| LOCAL_INTERCONNECT | base 粒度读写；两种编码模式破解；V2 安全防线 | 往返闭合 |
| R4 布线开关 | 25/37 个 I-index 已映射；剩余 12 条卡在语料 | 部分 |
| R24 长距离线 | I=0 固定字节模型，约 73% wire | 部分 |
| C16 长距离线 | — | 未开始 |
| 比特流编解码器 | LUT TT + 布线读写完成；往返自洽；V2 安全防线；CRC patcher 已整合 | 硬件验证 |
| 路由综合（绿区岛） | CE6 标准 15 岛 686/686 bit-perfect；越狱 / 边缘 9 岛 45/45 靠 snapshot fallback；总 harness 731/731 | 闭合（2026-04-14） |
| FASM sig-cache（Phase 4.5） | **38,683 条目**（2026-04-19 扩展）；7-tuple（支持 sn>0）；NEORV32 v2 路由 miss = 0 | 生产 |
| M9K init 编解码器（Phase 5.2） | 2D 线性公式；33+5 anchor（含 18×512）；M9K pipeline 端到端闭合（Yosys→prepack→np2fasm→fasm2rbf） | 硬件已验证（芯片接受开源工具链 M9K RBF，2026-04-16） |
| M9K_MODE（Phase 5.2） | `_inferred_goldintersect` 按 (w,d) 的站点不变集；np2fasm 发射门控 `_M9K_MODE_HW_VALIDATED = {(9,512),(18,512),(9,1024),(36,256)}`；(4,2048) 矽片失败（门控关闭） | 硬件已验证 4/5 宽度（2026-04-17, 2026-04-24） |
| GCLK 管线（Phase 5.4） | `GCLK_PIN`（F17 上 12 个 pin）+ `LAB_CLK_SEL` + `LAB_CLK_SEL_LE` N∈{0,2,4,6,8}；基于 AUTO baseline 做 XOR 合成 | 硬件验证（14 LAB × 5 N-slot；Stage 0 烧录 2026-04-16） |
| IOB FASM（Phase 5.4） | `IOB_IN`/`IOB_OUT` 44/44；`IOB_IN_BIDIR`/`IOB_OUT_BIDIR` 16 sdram_dq pin；`IOB_ROUTE` 双应用路径（默认配对派生 + Fix A `legacy_iob_route=True` 用于 single-LE 设计）；`single_le_cells` 109 条 Fix-B 在 legacy 路径下重挖；`IOB_OE` 16 pin | IOB_ROUTE 两条路径均硬件验证；BIDIR/OE codec 验证 + 矽片二分法 |
| DSPMULT（Phase 5.0） | 22 cell 矽片干净集（23 挖掘 − 1 经 frame 1729 二分法证伪） | 硬件二分法完成；np2fasm 未接线（NEORV32 使用 0 个 DSPMULT） |
| `nv_zero_global` 退役 | `NV_BASELINE_PACK` 指令 + 子指令从 PURE_ZERO 直接复现 Quartus baseline 的每一字节 | **矽片等价性已确认**（Stage 0 烧录 2026-04-16） |
| 公式化 LutCodec（σ⁻¹ 3-key） | `from_cram_model(x, y, n)` + 3-key σ⁻¹ 表（`(foff, fb8, group)`），**2,112 条**，5 级 fallback；Y=3 wrap + Group-4 fb8∈{0,1,3,4} 两个缺口于 2026-04-24 补齐 | 生产（2026-04-24）；残留 fb8=7 × group=4 受矽片几何限制（X=8 在 Y≥12 无 LAB） |
| 开源工具链 —— 原生路径（Phase 5.3） | Yosys → nextpnr-generic（chipdb 26 LOCAL tracks，3.6M pip）→ np2fasm → fasm2rbf。AND gate + 5-bit carry counter + M9K smoke 在单/跨 LAB 规模硬件验证通过 | 小/中规模硬件验证通过；chipdb 路由模型对 NEORV32 级密度仍过于稀疏 |
| ζ BIT 逃生通道（Phase 7） | `scripts/bit_workaround/quartus_gold_to_bit_fasm.py` + fasm2rbf 把任何 Quartus RBF 逐字节重建。NEORV32 用 127k 条 BIT；总耗时 0.5 秒 | 2026-04-23 在 AX301 端到端硬件验证通过（4712 LE / 19 M9K 的 NEORV32 bootloader） |

---

## 参考资料

- [Cyclone IV Device Handbook](https://www.intel.com/content/www/us/en/docs/programmable/683853/current/cyclone-iv-device-handbook.html)
- [Project IceStorm](http://www.clifford.at/icestorm/) — iCE40 逆向工程，方法论范本
- [Project Mistral](https://github.com/Ravenslofty/mistral) — Cyclone V 逆向工程，同家族参考
- [Quartus Prime Lite](https://www.intel.com/content/www/us/en/products/details/fpga/development-tools/quartus-prime/resource.html) — 免费 FPGA 开发工具

---

## 值得记住的死胡同

逆向工程多半是在搞清楚哪些看起来好看的假设是错的。下面这些是真正花掉
时间的那几条，记录在这里好让后来的人不必再踩：

- **M5 counter 的进位链弯路。** 通过开源工具链做了一个 24-bit
  counter，怎么也对不上 Quartus 的 RBF。花了一段时间先后修了
  `LutCodec`、
  重挖 sig-cache 条目、追查 `fasm2rbf` 的 phase-ordering bug。真正的
  root cause 完全不在那里 —— Quartus 用的是 nextpnr-generic 没有建模
  的 LE 内进位链连线，Yosys 把 `+1` 仿真成了 4-LE 波纹加法、带 24 条
  自反馈路由。沿途修的 codec bug 是真的 bug，但真正挡路的是缺失的
  primitive。教训：开源工具链出来的 D 设计行为异常时，**先**烧一份
  Quartus 的 D RBF 并做两份 bitstream 的 diff，再去动 codec。
- **IOB 跨轴线性叠加。** 听起来很合理的假设：驱动 (KEY_X, LED_Y) 的
  设计应该能分解为 (KEY_X only) ⊕ (LED_Y only) ⊕ baseline。被证伪
  —— bank-pair 查表同样失败。残差是大约 50-60 字节的 joint-placement
  状态，两个模型都抓不到。要收口只能跑一次完整的 2D K×LED 扫描（约
  480 次 pair build），目前在进行中。衍生模型不会回来了，不要重试。
- **R4 dark passive mining。** 尝试通过 NV32 整片 RBF 的 bit 密度
  恢复 R4 的 `BASE` 常量。RBF 太致密，信噪比低于挖掘阈值。死胡同。
- **T9 LI paired-vs-alternating 作为路由 key 的函数。** 挖过、结构
  审计过，结果被证伪 —— 这个选择**不是** `(src_type, src_I, dst_N,
  dst_port)` 的函数。停止在这条轴上继续挖，缺的变量在别处。
- **DFF 的每-LE enable CRAM bit。** 追了好一段时间才意识到 Cyclone IV 的
  FF 是矽片内生的、每个 LE 都有、没有 per-LE enable cell。原来的
  `dff_cells_mined.json` 是路由基础设施噪声，与任何真实设计都 0 重
  叠。FASM 的 `DFF` 指令如今是一个被解析的 no-op。
- **用两 LUT 配对模板挖 self-loop sig-cache。** 模板无法表示
  `src == dst`，而且 Quartus 在 baseline 与 feedback 两次编译之间会
  refit，diff 会包含与 LI MUX 无关的 pin 重排。`route_cells_full.json`
  里 61 条 self-loop 条目都是被虚胖的噪声（cell 数 90-754，语料中位
  数 135），重跑 factory 救不了。需要 single-LE differential 策略。

- **DSPMULT_GLOBAL_ON 23-cell 集 —— 在矽片上被证伪（2026-04-16）。**
  重挖后的 23 cell「通用块启用」看起来很干净：CRAM-only、CRC-strip、
  21/21 N-invariant、零路由漂移。Stage 0 烧入 AX301 → LED 常亮。
  四层二分法缩小到单个 cell `(363236, 2)` 在 frame 1729。清洗后的
  22 cell 集通过矽片验证。教训：即便「干净」的挖掘活动有稳定的交
  集，也可能藏着一个与无关 fabric 路径交互的 load-bearing cell。
  必须在解除 np2fasm 门控前做矽片验证。
- **IOB_OE PIN_R5 —— 矽片失败，已二分（2026-04-17）。**
  sdram_dq S_DB[0] 的 40 cell per-pin OE 集通过了所有 codec 安全门
  （与 simple_led_pure 零 fabric/hdr/block 重叠）。烧录 → LED 常亮。
  二分至 2 个 cell `(363236,2)+(363672,2)`；清洗后 38 cell 集通过。
  `(363236,2)` 与 DSPMULT 漏电共享 —— 看起来是 block-band 共性隐患。
- **LUT_ARITH_MULTI_LAB WIDTH=17 —— 矽片失败（2026-04-17）。**
  width 17..32 的多 LAB 进位链 blob 在 `diff` 下与 Quartus 输出逐字
  节一致（10/10 codec 测试），但烧录 → LED 常灭。失败模式与 IOB_OE
  不同（常亮 vs 常灭）。多 LAB blob 的位置无关性从未被证明（三角测
  试只覆盖了单 LAB width ≤16）。保持门控。
- **F16 输出路由 —— 已挖掘但无法集成（2026-04-19）。**
  差分挖掘（f16_loc vs f15_loc 在同一 X7Y21N14）干净地隔离了 40 个
  F16 特有 data cell（38 header + 2 block band）。LOC 约束的
  f16_loc.rbf 在 AX301 上硬件验证通过（LED1 对 K3∧K4 正确响应）。
  然而，仅向 pipeline 测试 RBF 添加 16 个新 cell 就触发 FPGA 重置
  —— 来自 `from_cram_model()` pair mapping 的累积 LUT 层损坏
  （192/233 LUT 错误）意味着基础设施已处于不良状态。F16 cell 本身
  正确；需要等 LUT 层修复后才能应用。

每一条都有独立的 post-mortem 记在
`~/.claude/projects/-home-test-EP4CE6/memory/` 底下 —— 搜索
`m5_counter_root_cause_carry_chain`、`iob_cross_axis_not_decomposable`、
`r4_dark_passive_mining_dead`、`t9_li_mode_negative_result`、
`dff_perle_formula`、`sigcache_mining_template_pitfall`、
`dspmult_global_on_clean_remine`、`iob_oe_r5_bisection_silicon`、
`f16_output_routing_mined`。

## 局限与不是什么

让 README 在进度之外，同样诚实地交代范围：

- **C16 长距离线 —— 未触及。** 零覆盖。当前所有路由工作都在 C4 / R4 /
  R24 / LI 上。会经 C16 走线的设计不被支持。
- **非 E 系列的 Cyclone IV 芯片 —— 未验证。** 本仓库每一次矽片验证都
  在 EP4CE6F17C8（AX301 板）上完成。codec 公式在
  EP4CE15/22/30/40/55/75/115 与 Cyclone IV GX 上都没有测过。E 系列
  内部 die 拓扑理应相似，但「应该相似」不是已经核对过的结论。
- **大型设计 —— 未端到端测试。** 开源流程硬件验证过的设计都很小（8
  位 counter、AND 门、identity-LED）。NEORV32 已经综合并 map 过，但
  没有任何一份由开源流程构建的 NEORV32 比特流被烧录、被证实能在矽片
  上 boot。更大的设计可能暴露小测试看不到的 codec / chipdb 缝隙。
- **温度与电压 corner —— 未表征。** 所有矽片验证都在室温、标称 Vccint
  下完成。工业温度范围与电压跌落下的行为没有测过。
- **开源流程里的 M9K BRAM —— 硬件尚未验证。** codec + `np2fasm` 发射
  已绿（各 5/5 测试），chipdb 有 M9K bel 与 bridge pip，但 Yosys 的
  `memory_libmap` 前端目前会拒掉（"can't share write port 0:
  incompatible enable" —— 一个 lib / memory-shape 不匹配的问题），
  挡住了 `tmp/m9k_smoke/ram_9x512.v` 的 smoke build。没有任何用到
  RAM 的设计从开源流程烧录过。
- **PLL —— 在 fabric 之外，不在范围内。** Cyclone IV 的 PLL 住在本项目
  没有映射的 CRAM 区域之外。需要配置 PLL 的设计（区别于 `GCLK_PIN`
  指令覆盖的专用时钟 pin）不被支持。
- **LutCodec `from_cram_model()` pair mapping —— 有 bug。** 公式在
  (10,10,0) 处产出正确的 minterm，但在其它位置 bit-to-cell pair 排列
  错误。pipeline 测试中 192/233 个 LUT 产生错误的真值表。这是烧录任何
  非 trivial 开源工具链设计的首要阻塞。pair 排列随 (x,y) 变化的方式
  尚未被公式捕获；修复需要逆向 pair 排列。
- **chipdb LOCAL 总线 —— 对密集设计容量不足。** 路由模型每个 LAB 只有
  4 条 LOCAL track（总计约 2080 wire）。真实 Cyclone IV 矽片有 O(100k)
  路由资源（C4/R4/R24/LI crossbar）。在 6500+ LE（NEORV32 规模）下
  几乎每条 LOCAL wire 都过度使用，导致驱动冲突和 FPGA 保护性重置。这
  是路由模型的根本局限，不是指令 bug。修复选项：SIG-cache 感知放置、
  分层路由模型、或专用 nextpnr-cyclone4 架构移植。
- **不是 Quartus 的替代品。** 这个 codec 不是 timing-driven 布局布线
  工具。它独有的能力是对已发布比特流做 bit-level 双向修改与离线
  mutation / replay —— 见前面的《长期方向》。如果需要 PPA-competitive
  综合，请使用 Quartus。

---

## 许可证

2026-04-07 起的双许可证（替换原先的 MIT）：

- **代码**（`fuzz/`、`synth/`、`scripts/`，所有可执行的部分）——
  `GPL-3.0-or-later`。完整文本：
  [`LICENSES/GPL-3.0-or-later.txt`](LICENSES/GPL-3.0-or-later.txt)。
- **文档与论述**（`README*.md`、`CLAUDE.md`、`FINDINGS.md`、`docs/`）
  —— `CC BY-SA 4.0`。完整文本：
  [`LICENSES/CC-BY-SA-4.0.txt`](LICENSES/CC-BY-SA-4.0.txt)。

**copyleft 盖住什么，盖不住什么。** GPL 以软件身份绑定在代码上，
CC BY-SA 以书面作品身份绑定在论述上 —— 两者都要求下游对这些工件的
fork 继续保持相同条款。但**方法论本身**不在任何一个许可证的覆盖范围
内：逆向工程的技巧、CRAM 公式、bit 偏移、CE10 越狱结果都是**事实**，
不是表达，版权法本来就圈不住它们。我们仍然选了 copyleft，是因为这样
可以让参考实现和书面档案继续开放 —— 这是下游真正会依赖的部分。如果
想让方法论挂到更可追溯的权利声明上，引用仓库与对应的 `FINDINGS.md`
条目就够了 —— 这才是 defensive publication 的样子。

Bitstream 原始档（`*.rbf`、`*.sof`）、SQLite 语料，以及 `work/` 和
`results/rbf/` 里的 Quartus 产物属于硬件遥测、不是创作品，本项目不对
它们主张版权；其再分发仍受 Altera/Intel 原始工具授权条款约束。

本项目仅用于教育与研究目的。
