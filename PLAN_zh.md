# EP4CE6 Bitstream 逆向工程：自動化黑箱 Fuzzing 可行性分析與實施計劃

## Context

目標：對 Altera Cyclone IV EP4CE6F17C8 的 bitstream (.rbf) 格式進行完整逆向工程，建立從邏輯配置到繞線矩陣的完整位元映射字典，最終對接開源工具鏈 (Yosys + NextPNR)。

### 已有基礎設施
- **Quartus 21.1 Lite**: `$HOME/intelFPGA_lite/21.1/` (quartus_map/fit/asm/cpf 全部可用)
- **硬體**: 黑金 AX301 開發板, EP4CE6F17C8 (6,272 LEs, 392 LABs, 30 DSP multipliers)
- **已有 RBF 檔案**: riscv_tpu_demo (368,011 bytes), bitcoin_miner, led_funcmod — 全部尺寸一致
- **openFPGALoader**: 從源碼編譯，支持 EP4CE6
- **Python 環境**: pyusb, pyserial, numpy
- **Cyclone IV Handbook**: `docs/cyclone4-handbook.pdf` (Cyclone IV 架構手冊)
- **工作目錄**: 項目根目錄 (空目錄，已建立)

### RBF 格式已知事實
- 固定大小: **368,011 bytes = 2,944,088 bits**
- 前導: 32 bytes 0xFF | 配置數據: 367,920 bytes | 尾部: 59 bytes 0xFF
- 兩個完全不同的設計 (TPU vs Bitcoin) 差異: ~212,556 bits (約 7.2%)
- 必須用 `quartus_cpf -c -o bitstream_compression=off` 生成，不可用 sof2rbf.py

### EP4CE6 晶片幾何
- **392 個 LAB**, 每個 LAB 含 **16 個 LE**
- LAB X 座標: 22 個值 [3,4,6,7,8,10,11,12,13,16,17,18,19,21,22,23,24,25,26,28,29,31]
- LAB Y 座標: 18 個值 [2-14,16-19,21]
- LE N 索引: 偶數 [0,2,4,...,30]
- 節點命名: `LCCOMB_X<col>_Y<row>_N<le_idx>` (組合邏輯), `LCFF_X<col>_Y<row>_N<le_idx>` (暫存器)
- 繞線資源: Block 32,401 / Local 10,320 / C4 21,816 / C16 1,326 / R4 28,186 / R24 1,289

---

## 可行性總結

| 階段 | 可行性 | 風險 | 編譯量估算 |
|------|--------|------|-----------|
| Phase 1: Fuzzing 管線 | **高** ✓ | 低 — 所有工具已驗證可無頭運行 | ~50 次 (基礎架構) |
| Phase 2: 邏輯配置破解 | **高** ✓ | 低 — 純粹的 diff 分析 | ~7,500 次 (~24 hr) |
| Phase 3: 繞線矩陣 | **中高** | 中 — 無法直接控制繞線路徑 | ~50,000-100,000 次 |
| Phase 4: 開源工具整合 | **中** | 中 — 依賴 Phase 2+3 完整度 | 軟體工程為主 |

**單次編譯時間估算**: 極簡設計 ~8-12 秒 (map+fit+asm+cpf)，約 300-450 次/小時。

---

## Phase 1: 自動化黑箱 Fuzzing 管線

### 目錄結構
```
./
├── fuzz/
│   ├── config.py          # EP4CE6 常數 (LAB 座標, 路徑, 腳位)
│   ├── verilog_gen.py     # 生成極簡 Verilog
│   ├── qsf_gen.py         # 生成 QSF + 放置約束
│   ├── compile.py         # 驅動 Quartus 無頭編譯
│   ├── rbf_diff.py        # 二進制 diff 引擎
│   ├── database.py        # SQLite 位元映射資料庫
│   ├── runner.py          # 編排 fuzzing 戰役
│   └── analyze.py         # 結果分析與視覺化
├── templates/
│   └── fuzz_top.v         # Verilog 模板
├── results/
│   ├── rbf/               # 收集的 .rbf 檔
│   └── ep4ce6_bitdb.sqlite
└── work/                  # Quartus 臨時編譯目錄
```

### 核心元件

#### 1. Verilog 生成器 (`verilog_gen.py`)
生成只包含一個 LUT4 的極簡設計，透過參數化真值表表達式控制邏輯功能：

```verilog
module fuzz_top(
    input  wire A, B, C, D,
    output wire Q
);
    wire lut_out /* synthesis keep */;
    assign lut_out = {EXPRESSION};  // e.g. A & B, A | B, A ^ B
    assign Q = lut_out;
endmodule
```

16 個基本真值表位元的對應表達式：
- Bit 0: `~A & ~B & ~C & ~D`
- Bit 1: `~A & ~B & ~C & D`
- ... (每個 minterm 一個)
- Bit 15: `A & B & C & D`

#### 2. QSF 生成器 (`qsf_gen.py`)
關鍵 QSF 設定：
```tcl
# 裝置設定
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top

# 關閉所有優化 (防止 Quartus 改變我們的邏輯)
set_global_assignment -name AUTO_RAM_RECOGNITION OFF
set_global_assignment -name AUTO_DSP_RECOGNITION OFF
set_global_assignment -name AUTO_SHIFT_REGISTER_RECOGNITION OFF
set_global_assignment -name ALLOW_REGISTER_RETIMING OFF
set_global_assignment -name SYNTH_TIMING_DRIVEN_SYNTHESIS OFF

# 強制放置到指定 LE
set_location_assignment LCCOMB_X{x}_Y{y}_N{n} -to "lut_out"

# I/O 腳位 (使用 AX301 上可用的 GPIO)
set_location_assignment PIN_E1 -to CLK
set_location_assignment PIN_M2 -to A
...
```

#### 3. 編譯驅動 (`compile.py`)
```bash
quartus_map --read_settings_files=on --write_settings_files=off fuzz_proj -c fuzz_proj
quartus_fit --read_settings_files=on --write_settings_files=off fuzz_proj -c fuzz_proj
quartus_asm --read_settings_files=on --write_settings_files=off fuzz_proj -c fuzz_proj
quartus_cpf -c -o bitstream_compression=off output_files/fuzz_proj.sof fuzz_proj.rbf
```

**重要優化**: 只改 QSF 放置約束 (不改 Verilog) 時，可跳過 `quartus_map`，只跑 `quartus_fit` + `quartus_asm` + `quartus_cpf`。

#### 4. 節點名稱發現 (兩步驟法)
1. 第一次編譯不加放置約束，讓 Quartus 自由擺放
2. 用 `quartus_cdb` 的 Tcl API 跑 `get_names -filter * -node_type comb` 找到 LUT 實際節點名
3. 後續所有編譯都用發現的節點名做 `set_location_assignment`

#### 5. Diff 引擎 (`rbf_diff.py`)
逐 bit 比較兩個 RBF，輸出所有翻轉位元的 (byte_offset, bit_position, direction)。

#### 6. SQLite 資料庫 (`database.py`)
表結構:
```sql
CREATE TABLE bit_mapping (
    x INTEGER, y INTEGER, n INTEGER,
    feature TEXT,  -- 'lut_bit_0', 'lut_bit_1', ..., 'ff_enable', 'route_c4_xxx'
    byte_offset INTEGER,
    bit_position INTEGER,
    PRIMARY KEY (x, y, n, feature, byte_offset, bit_position)
);
```

---

## Phase 2: 破解邏輯配置

### Step 2.1: LUT 真值表位元 (最先嘗到甜頭)
1. 編譯空設計 → `baseline.rbf`
2. 在固定座標 (例如 X=10, Y=10, N=0) 放置 16 個不同的 minterm 設計
3. 每個 vs baseline 做 diff → 找出控制每個真值表位元的 bitstream 位置
4. 驗證: 編譯 `A & B` (mask=0x8888)，確認 diff 結果等於 bit 3,7,11,15 的聯集

**預期結果**: 每個 LE 有 16 個 bit 直接編碼真值表。

### Step 2.2: LAB 網格映射
1. 選一個固定函數 (A & B)
2. 依序放置在所有 6,272 個 LE 位置
3. 真值表位元應出現在不同的 bitstream 偏移量
4. 繪製 offset vs (X, Y, N) → 發現位址映射公式

**預期結構**: Bitstream 按列 (column) 組織，每列 LAB 映射到連續區域。

### Step 2.3: LE 模式位元
- Normal mode (組合邏輯 LUT4)
- Arithmetic mode (進位鏈)
- Register modes (同步/非同步 clear/load)
- 每個模式在已知位置各編譯一次，diff 找出模式控制位元

---

## Phase 3: 繞線矩陣 (最大挑戰)

### 核心困難
Quartus Lite **沒有** 直接的繞線路徑控制 API。無法指定 "信號 X 必須經過 C4 線 #37"。

### 間接控制策略

**策略 A: 距離推斷法**
- 在 (X1,Y1) 放 driver LUT，在 (X2,Y2) 放 load LUT
- 控制距離來強制使用特定繞線資源類型：
  - 相鄰 LAB → direct links
  - 同列 1-4 行 → C4 wires
  - 同列 5-16 行 → C16 wires
  - 同行 1-4 列 → R4 wires
  - 同行 5-24 列 → R24 wires

**策略 B: 多扇出法**
- 一個 driver + 多個策略性放置的 load → 強制使用特定 switch box
- 與單 load 設計做 diff → 隔離額外的繞線位元

**策略 C: `ROUTE_REGION` 約束**
- 限制繞線在特定區域，間接強制使用特定資源

**策略 D: 事後分析 (Post-fit Tcl)**
- 編譯後用 `quartus_cdb` 讀取 fitter 資料庫中的實際繞線結果
- 將繞線報告與 bitstream diff 做關聯分析

### 風險: 繞線非確定性
- 相同放置可能產生不同繞線路徑
- 緩解: `quartus_fit --seed=N` 控制隨機種子
- 緩解: `ROUTER_TIMING_OPTIMIZATION_LEVEL MINIMUM`
- 需要統計分析來解決模糊位元

---

## Phase 4: 開源工具整合 (長期)

### FASM/Bitgen 工具
- 輸入: FASM 文字檔 (列出所有啟用的 feature)
- 查表: 從 SQLite 字典找對應位元
- 輸出: 368,011 bytes RBF 檔

### NextPNR 後端
- 需要: Cyclone IV 架構描述 (C++)、packer、place-and-route 適配
- 參考: NextPNR 的 iCE40 和 ECP5 後端，各數千行 C++

---

## 先行技術參考

| 專案 | 目標晶片 | 方法 | 與本案相關度 |
|------|----------|------|-------------|
| Project IceStorm | Lattice iCE40 | icecube2 + fuzzing | 高 — 方法論完全相同 |
| Project X-Ray | Xilinx 7-series | Vivado + specimen fuzzing | 高 — FASM 格式可參考 |
| Project Mistral | Altera Cyclone V | quartus_cdb + Tcl | **極高** — 同家族晶片 |
| Project Trellis | Lattice ECP5 | Diamond + fuzzing | 中 — 繞線策略可參考 |

**Mistral (Cyclone V)** 最具參考價值：同為 Altera 晶片，CRAM 組織方式類似，且作者也是用 quartus_cdb Tcl API 做事後分析。

---

## 建議的立即行動 (Phase 1 實作順序)

1. **建立專案骨架**: `./fuzz/` 目錄結構
2. **寫 `config.py`**: 硬編碼所有 LAB 座標和裝置常數
3. **寫 `verilog_gen.py`**: 參數化 LUT4 Verilog 生成
4. **寫 `qsf_gen.py`**: 生成包含放置約束的 QSF
5. **寫 `compile.py`**: 驅動 Quartus 無頭編譯流程
6. **第一次實驗**: 空 baseline + 16 個單 bit 真值表設計 → 驗證能找到 16 個 LUT truth table bits
7. **寫 `rbf_diff.py` + `database.py`**: 結果存入 SQLite
8. **擴展到整個 LAB**: 16 LE × 16 函數 = 256 次編譯
9. **擴展到整個晶片**: 392 LAB × 1 函數 = 6,272 次編譯 → 建立完整網格映射

### 關鍵參考檔案
- `riscv_tpu_demo.qsf`（外部參考）— QSF 參考
- `AX301.tcl`（外部參考）— AX301 腳位分配
- `docs/cyclone4-handbook.pdf` (Cyclone IV 架構手冊) — Cyclone IV 架構手冊

### 驗證方法
1. 第一個 milestone: 成功在指定座標放置 LUT 並編譯出 RBF
2. 第二個 milestone: 兩個不同 LUT 函數的 RBF diff 只有少量 bit 不同
3. 第三個 milestone: 16 個 minterm 各找到獨立的真值表位元
4. 第四個 milestone: 相同函數放在不同 LE，真值表位元出現在不同 offset
5. 最終驗證: 手動修改 RBF 中的真值表位元 → 燒入硬體 → 觀察邏輯行為改變
