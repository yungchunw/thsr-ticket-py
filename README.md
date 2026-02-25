# 高鐵訂票小幫手

**!!--純研究用途，請勿用於不當用途--!!**

> Fork 自 [BreezeWhite/THSR-Ticket](https://github.com/BreezeWhite/THSR-Ticket)，感謝原作者。

此程式提供命令列介面的高鐵訂票工具。支援自動辨識驗證碼、刷票搶票、會員購票等功能。

---

## 安裝

### 推薦：使用 uv（全域安裝為 CLI 工具）

```bash
# 安裝 uv（若尚未安裝）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 從原始碼安裝
git clone https://github.com/BreezeWhite/THSR-Ticket.git
cd THSR-Ticket
uv tool install .
```

安裝後可直接在終端機使用 `thsr-ticket` 指令。

### 開發環境

```bash
git clone https://github.com/BreezeWhite/THSR-Ticket.git
cd THSR-Ticket
uv sync
uv run thsr-ticket
```

---

## 使用方式

### 互動模式（最簡單）

```bash
thsr-ticket
```

程式會逐步詢問車站、日期、時間、票數等資訊，並自動辨識驗證碼完成訂票。

### 指定參數（適合熟悉使用者）

```bash
thsr-ticket -f 2 -t 12 -d 2026/03/01 -T 10 -a 1 -i A123456789
```

---

## 參數說明

| 參數 | 說明 | 範例 |
| --- | --- | --- |
| `-f`, `--from-station` | 啟程站 ID | `-f 2`（台北） |
| `-t`, `--to-station` | 到達站 ID | `-t 12`（左營） |
| `-d`, `--date` | 出發日期 | `-d 2026/03/01` |
| `-T`, `--time` | 出發時間 ID | `-T 10`（09:30） |
| `-a`, `--adult-count` | 成人票數 | `-a 2` |
| `-s`, `--student-count` | 大學生票數 | `-s 1` |
| `-i`, `--personal-id` | 身分證字號 | `-i A123456789` |
| `-P`, `--phone` | 手機號碼 | `-P 0912345678` |
| `-p`, `--seat-prefer` | 座位偏好（0:無、1:靠窗、2:走道） | `-p 1` |
| `-c`, `--class-type` | 車廂類型（0:標準、1:商務） | `-c 0` |
| `-m`, `--use-membership` | 使用高鐵會員身分 | `-m` |
| `-C`, `--no-auto-captcha` | 停用自動辨識，改為手動輸入驗證碼 | `-C` |
| `--snatch-end` | 刷票模式結束日期（見下方說明） | `--snatch-end 2026/03/07` |

### 查詢指令

```bash
thsr-ticket --list-station      # 列出所有車站與 ID
thsr-ticket --list-time-table   # 列出所有時間選項與 ID
```

### 車站 ID

| ID | 站名 | ID | 站名 |
| --- | --- | --- | --- |
| 1 | 南港 | 7 | 台中 |
| 2 | 台北 | 8 | 彰化 |
| 3 | 板橋 | 9 | 雲林 |
| 4 | 桃園 | 10 | 嘉義 |
| 5 | 新竹 | 11 | 台南 |
| 6 | 苗栗 | 12 | 左營 |

---

## 刷票模式（搶票）

連假、春節等熱門時段票很快售罄。刷票模式會**逐日嘗試**，找到有票的日期後自動完成訂票。

```bash
# 搶台北→左營，2/28 到 3/5 之間任何一天
thsr-ticket -f 2 -t 12 -d 2026/02/28 --snatch-end 2026/03/05 -a 1 -i A123456789

# 加上時間限制：只找上午班次（--time 9 = 09:00 之後）
thsr-ticket -f 2 -t 12 -d 2026/02/28 --snatch-end 2026/03/05 -T 9 -a 1 -i A123456789
```

**流程說明：**

1. 從 `--date` 指定的日期開始，逐日嘗試
2. 查無班次 → 自動換下一天
3. 找到班次 → 自動選第一班，完成訂票
4. 全部日期皆無班次 → 顯示失敗訊息

> **提示：** 刷票模式建議同時指定所有常用參數（`-f -t -a -i` 等），避免進入互動提示。`--time 1` 可從 00:01 起搜尋所有班次。

---

## 自動辨識驗證碼

本程式內建 CNN 模型自動辨識驗證碼，**預設開啟**，無需手動輸入。

- 辨識失敗時自動重試（最多 30 次）
- 每次訂票的驗證碼圖片會自動儲存至 `thsr_ticket/ml/train/data/raw/`，可用於模型增量訓練

### 停用自動辨識

```bash
thsr-ticket -C   # 或 --no-auto-captcha
```

停用後程式會開啟驗證碼圖片，等待手動輸入。

---

## 歷史紀錄

每次成功訂票後，程式會儲存常用資訊（車站、時間、身分證、電話），下次啟動時可直接選擇快速填入。

---

## 功能列表

| 功能 | 狀態 |
| --- | --- |
| 選擇啟程／到達站 | ✅ |
| 選擇出發日期、時間 | ✅ |
| 選擇成人票數 | ✅ |
| 選擇大學生票數 | ✅ |
| 選擇座位偏好（靠窗／走道） | ✅ |
| 選擇車廂類型（標準／商務） | ✅ |
| 自動辨識驗證碼 | ✅ |
| 會員購票 | ✅ |
| 早鳥票預訂 | ✅ |
| 儲存歷史紀錄 | ✅ |
| 刷票搶票模式 | ✅ |
| 輸入孩童／愛心／敬老票數 | ❌ |
| 輸入護照號碼 | ❌ |

---

## 訓練驗證碼模型

詳見 [thsr_ticket/ml/train/README.md](thsr_ticket/ml/train/README.md)
