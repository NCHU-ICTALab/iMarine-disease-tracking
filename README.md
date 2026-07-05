# 疫情自動追溯與擴散圈風險預警（後端 MVP）

對應報告書主軸三（港邊工作人員視角）＞「疫情擴散圈風險預警」。
重建進港船的靠港序列，交叉比對疫情時序，以規則式評分輸出風險等級與防護建議，
並以（mock）細胞簡訊推播。純後端 + 資料庫，聚焦**高雄港（TWKHH）進港船**。

## 架構（五層資料流，後端精簡版）

```
來源層  AIS(mock/aisstream) · 疾管署CSV · WHO DON API
   │
治理層  清洗/去重 · 船舶識別碼統一 · UN/LOCODE 座標與國別對齊 · Grounding 來源標註
   │
分析層  ① 航跡重建  ② 時序交叉比對  ③ 規則式風險評分(IHR/病原規則表)
   │
服務層  即時風險資料庫 · REST API · 細胞簡訊推播(mock)
```

## 目錄

| 路徑 | 說明 |
|---|---|
| `app/sources/` | 來源層：`ais_provider`、`cdc_scraper`、`who_scraper` |
| `app/governance/` | 治理層：`ports`(港口主檔)、`countries`(國名→ISO)、`outbreaks`(正規化/去重) |
| `app/analysis/` | 分析層：`track_builder`、`matcher`、`risk_engine`、`pathogens`(病原規則表) |
| `app/service/` | 服務層：`api`(路由)、`notifier`(推播 mock) |
| `app/jobs/scheduler.py` | APScheduler 定時抓取/重算 |
| `app/pipeline.py` | 高階編排：抓取 → 比對評分 → 寫回 |
| `data/` | `ports_seed.csv`、`mock_ais.json`、`pathogens.yaml` |
| `scripts/` | 見下方「腳本說明」 |
| `tests/` | pytest（19 項） |

## 快速開始

```bash
# 1. 建立虛擬環境並安裝
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 2. 初始化 DB + 載入港口主檔 + 匯入 mock AIS 靠港序列
.venv\Scripts\python scripts/seed.py

# 3. 抓一次最新疫情 + 全量重算 + 輸出結果（最常用）
.venv\Scripts\python scripts/run_latest.py
#    → 結果寫入 demo_output.json

# 4. 啟動 API
.venv\Scripts\python -m uvicorn app.main:app --reload
#    文件：http://127.0.0.1:8000/docs
```

> 設 `ENABLE_SCHEDULER=1` 可在啟動時掛載定時抓取/重算。

## 腳本說明（`scripts/`）

所有腳本都在專案根目錄執行，例如 `.venv\Scripts\python scripts/run_latest.py`。

| 腳本 | 做什麼 | 何時用 | 是否連外網 |
|---|---|---|---|
| `seed.py` | 初始化資料庫、載入 24 個港口主檔、匯入模擬船靠港序列 | **第一次設定**時先跑一次 | 否 |
| `run_latest.py` | **抓一次最新疫情（疾管署 + WHO）→ 匯入 AIS → 全量評估 → 高風險推播 → 寫出 `demo_output.json`** | 想更新資料、看最新結果（等同 `POST /jobs/refresh`） | ✅ 是 |
| `export_demo.py` | 用**資料庫現有資料**重算並輸出 `demo_output.json`（不重抓疫情） | 只想重出結果、不需更新疫情時 | 否 |
| `demo_assess.py` | 在終端機印出評估過程與**可解釋計分明細**（含各維度分數、衰減） | 想了解「分數是怎麼算出來的」 | 否 |
| `probe_sources.py` | 直接打疾管署 CSV 與 WHO API，印出**原始欄位與樣本** | 檢查資料來源是否正常、欄位有無變動 | ✅ 是 |
| `collect_ais.py` | 連 **aisstream.io** 即時串流一次，偵測靠港並累積到 `data/ais_sightings.json` | 用真實 AIS 時，多次執行/掛排程讓靠港序列補齊 | ✅ 是 |
| `collect_ais_loop.py` | **持續**收集數小時（每輪收集+間隔），不斷累積 sightings | 想在本機長時間累積真實靠港序列時 | ✅ 是 |

**一般流程**：第一次 `seed.py` → 之後每次要看最新結果就 `run_latest.py` → 打開 `demo_output.json` 看。

## 主要 API

| Method | Path | 說明 |
|---|---|---|
| GET | `/health` | 健康檢查 |
| GET | `/assessments?min_level=high` | 即時風險資料庫（每船最新，**標準輸出格式**） |
| GET | `/assessments/{ship_code}` | 單船評估（標準輸出格式，單筆） |
| GET | `/ships/{ship_code}/track` | 靠港序列 |
| GET | `/outbreaks?country=&since=` | 疫情事件 |
| POST | `/assess/{ship_code}` | 手動觸發單船評估（回傳單筆標準格式） |
| POST | `/jobs/refresh` | 一鍵抓取 + 全量重算（高風險自動推播），回傳標準輸出格式 |
| GET | `/notifications` | 推播紀錄（mock） |

## 標準輸出格式

整個 workflow 的輸出統一為此格式（API 的 `/assessments`、`/jobs/refresh` 與
`scripts/export_demo.py` 皆相同，範例見 [`demo_output.json`](demo_output.json)）。
格式由 `app/service/presenter.py` 集中產生；每船只保留重點欄位，
`matched_outbreaks` 取分數最高的前 3 筆並附來源可溯連結。

```jsonc
{
  "generated_at": "2026-07-03T00:00:00",
  "target_port": "TWKHH (高雄港)",
  "data_note": "疫情為真實資料（疾管署 / WHO），船舶航跡為模擬資料。詳見 docs/資料來源與真假對照.md",
  "assessments": [
    {
      "ship_code": "OCEANDUKE07",          // 船隻代碼
      "ship_name": "Ocean Duke",
      "prev_port": "SGSIN",                 // 前一個外國港
      "risk_level": "high",                 // low | medium | high | critical
      "score": 0.565,
      "matched_outbreaks": [                // 比對到的真實疫情（前 3 筆）
        {
          "port": "INBOM", "country": "IN",
          "disease": "Nipah virus disease",
          "report_date": "2026-06-25",
          "relation": "post_departure",     // during_or_before | post_departure
          "source": "who",
          "source_url": "https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON609"
        }
      ]
    }
  ]
}
```

- 單船端點（`/assessments/{ship_code}`、`/assess/{ship_code}`）回傳上方 `assessments[]` 的**單一元素**。
- `matched_outbreaks` 筆數由 `presenter.DEFAULT_MAX_MATCHES` 控制（預設 3）。
- `recommendation`（防護建議）目前**不放進輸出格式**，但仍會計算並存入資料庫（`risk_assessments.recommendation`），之後要用可再從 presenter 加回。

## 風險評分（規則式，可解釋）

五個維度加權（總和 1）後乘上近因衰減：

| 維度 | 權重 | 來源 |
|---|---|---|
| transmissibility（對港邊人員人傳人風險） | 0.30 | `pathogens.yaml` |
| severity（嚴重度 + PHEIC 加成） | 0.25 | `pathogens.yaml` |
| temporal_fit（時序吻合度） | 0.25 | `matcher` |
| stay（停留時間） | 0.10 | `port_calls` |
| recency（通報時效性） | 0.10 | `report_date` |

- 近因衰減：前一外國港權重 1.0，往前每站 ×0.7。
- 等級門檻：`≥0.75 critical`、`≥0.55 high`、`≥0.35 medium`、其餘 `low`。
- **新病原**只需在 `pathogens.yaml` 補一列規則，不需改程式、不需重訓（報告書 P.12）。

## 資料來源（已查證）

- 疾管署 國際旅遊疫情建議等級表 CSV（結構化主軸，含 ISO 國別碼/等級/日期）
- WHO Disease Outbreak News（OData JSON，權威補強 + PHEIC）
- 港口主檔：`data/ports_seed.csv`（可換 improved-un-locodes）
- AIS：**aisstream.io 即時串流**（`AIS_PROVIDER=aisstream`，真實船位）；或 `data/mock_ais.json`（`AIS_PROVIDER=mock`，可重現 demo）
  - ⚠️ aisstream 只給即時船位、無航跡歷史；系統以「港口鄰近+低船速」偵測靠港並累積到 `data/ais_sightings.json`，序列隨排程逐步補齊。詳見 [`docs/資料來源與真假對照.md`](docs/資料來源與真假對照.md)

> **哪些是真資料、哪些是測試假資料、各自來源與時間** → 見 [`docs/資料來源與真假對照.md`](docs/資料來源與真假對照.md)。
> 更完整的來源分析見上層 `../疫情自動追溯_實作計畫.md` §8。

## 測試

```bash
.venv\Scripts\python -m pytest tests -q
```

涵蓋：航跡重建與回溯窗口、三種時序關係（含報告書 P.8「離港後才通報」缺口）、
潛伏期窗口過濾、傳播途徑差異化評分、等級門檻、去重、推播門檻、REST API。

## 不在此範圍

真實付費 AIS、真實細胞廣播（CBS）、前端 UI、ML 模型；
以及 plan.md「船離臺 14 天內發病往前推」的 backfill（依需求排除）。
