# 高鐵訂票小幫手

**!!--純研究用途，請勿用於不當用途--!!**

> Fork 自 [BreezeWhite/THSR-Ticket](https://github.com/BreezeWhite/THSR-Ticket)，感謝原作者。

命令列介面的高鐵訂票工具。支援自動辨識驗證碼、搶票輪詢、指定車次、會員購票等功能。

---

## 安裝

### 推薦：使用 uv（全域安裝為 CLI 工具）

```bash
# 安裝 uv（若尚未安裝）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 從原始碼安裝
git clone https://github.com/yungchunw/thsr-ticket-py.git
cd thsr-ticket-py
uv tool install .
```

安裝後可直接在終端機使用 `thsr-ticket` 指令。

### 開發環境

```bash
git clone https://github.com/yungchunw/thsr-ticket-py.git
cd thsr-ticket-py
uv sync
uv run thsr-ticket
```

---

## 使用方式

### 互動模式（最簡單）

```bash
thsr-ticket
```

程式會逐步以方向鍵選單詢問車站、日期、時間、票數等資訊，並自動辨識驗證碼完成訂票。

### 指定參數

```bash
thsr-ticket -f 2 -t 12 -d 2026/03/01 -T 10 -a 1 -i A123456789
```

---

## 參數說明

### 訂票參數

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

### 搶票參數

| 參數 | 說明 | 範例 |
| --- | --- | --- |
| `--snatch` | 當天搶票：同一天持續重試直到有票 | `--snatch` |
| `--snatch-end` | 跨日搶票：從 `--date` 逐日搜尋到此日期 | `--snatch-end 2026/03/07` |
| `--snatch-interval` | 輪詢間隔（秒）；查無票時持續輪詢 | `--snatch-interval 30` |
| `--train-id` | 指定搶特定車次號碼 | `--train-id 663` |
| `--dry-run` | 模擬模式：完整執行流程但不實際送出訂位 | `--dry-run` |

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

## 搶票模式

連假、春節等熱門時段票很快售罄。搶票模式提供兩種方式：

### 當天搶票

指定日期持續重試，直到搶到票為止。

```bash
# 搶 2026/03/01 台北→左營，每 30 秒重試一次
thsr-ticket --snatch -f 2 -t 12 -d 2026/03/01 --snatch-interval 30 -a 1 -i A123456789
```

### 跨日搶票

從起始日期逐日嘗試，找到有票的日期後自動完成訂票。

```bash
# 搶 2/28 到 3/5 之間任何一天，每 60 秒輪詢一輪
thsr-ticket -f 2 -t 12 -d 2026/02/28 --snatch-end 2026/03/05 --snatch-interval 60 -a 1 -i A123456789
```

### 指定車次

搶到有票的班次後，可從清單中選擇目標車次（互動模式），或透過 `--train-id` 直接指定。

```bash
thsr-ticket --snatch -f 2 -t 12 -d 2026/03/01 --train-id 663 -a 1 -i A123456789
```

### 模擬測試

使用 `--dry-run` 可完整測試搶票流程（真實 HTTP、驗證碼、班次選擇），但不實際送出訂位。

```bash
thsr-ticket --snatch --dry-run --snatch-interval 5
```

---

## 設定檔

常用參數可寫入 `~/.thsr.toml`，CLI 參數優先於設定檔。

```toml
from_station = 2
to_station = 12
adult_count = 1
personal_id = "A123456789"
phone = "0912345678"
seat_prefer = 1
```

---

## 自動辨識驗證碼

內建 CNN 模型自動辨識驗證碼，**預設開啟**，無需手動輸入。

- 辨識失敗時自動重試（最多 30 次）
- 每次訂票的驗證碼圖片會自動儲存至 `thsr_ticket/ml/train/data/raw/`，可用於模型增量訓練

停用自動辨識：

```bash
thsr-ticket -C
```

停用後程式會開啟驗證碼圖片，等待手動輸入。

---

## 歷史紀錄

每次成功訂票後，程式會儲存常用資訊（車站、時間、身分證、電話），下次啟動時可直接選擇快速填入，也可在選單中勾選刪除舊紀錄。

---

## 功能列表

| 功能 | 狀態 |
| --- | --- |
| 方向鍵互動選單 | ✅ |
| 選擇啟程／到達站 | ✅ |
| 選擇出發日期、時間 | ✅ |
| 成人／大學生票數 | ✅ |
| 座位偏好（靠窗／走道） | ✅ |
| 車廂類型（標準／商務） | ✅ |
| 自動辨識驗證碼 | ✅ |
| 身分證格式與檢查碼驗證 | ✅ |
| 會員購票（TGo） | ✅ |
| 早鳥票預訂 | ✅ |
| 儲存／刪除歷史紀錄 | ✅ |
| 當天搶票模式 | ✅ |
| 跨日搶票模式 | ✅ |
| 指定車次搶票 | ✅ |
| 搶票輪詢間隔設定 | ✅ |
| 設定檔支援（~/.thsr.toml） | ✅ |
| 模擬模式（dry-run） | ✅ |
| 孩童／愛心／敬老票 | ❌ |
| 護照號碼 | ❌ |

---

## 訓練驗證碼模型

詳見 [thsr_ticket/ml/train/README.md](thsr_ticket/ml/train/README.md)
