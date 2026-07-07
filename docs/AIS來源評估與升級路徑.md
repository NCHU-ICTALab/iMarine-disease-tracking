# AIS 來源評估與升級路徑

> 目的：找出能讓風險模型**真正運作**的 AIS 來源，並說明接進系統要改哪裡。
> 背景結論見 [`資料來源與真假對照.md`](資料來源與真假對照.md)：免費 aisstream 無法提供
> 「高雄涵蓋」與「跨國前一港」，做不出有風險分數的真實 demo。

## 一、風險模型到底需要什麼？

分析層 `track_builder.prev_foreign_call()` 需要每艘抵達目標港的船的**歷史靠港序列**，
才能抓出「前一個外國港」去比對疫情。所以理想 AIS 來源必須具備：

1. **目標港（高雄／基隆）的即時抵港船清單**（真實涵蓋，含 MMSI/IMO/船名）。
2. **每艘船的歷史靠港紀錄（port calls / voyage history）** ← 這是關鍵，免費即時串流沒有。
3. （加分）衛星涵蓋，補足陸基接收站的盲區（高雄）。

## 二、來源比較

| 來源 | 即時位置 | 歷史靠港(port calls) | 衛星涵蓋 | 高雄涵蓋 | 價格級距 | 學術/免費方案 |
|---|---|---|---|---|---|---|
| **aisstream.io**（現用） | ✅ | ❌ | ❌ 陸基眾包 | ❌ 無 | 免費 | 免費即用 |
| **AISHub** | ✅ | ❌ | ❌ 陸基 | ❌（須自建站） | 免費 | 須貢獻一台接收器 |
| **Datalastic** | ✅ | ✅ vessel history / port calls | 部分 | 🟡 佳（陸基+彙整） | 便宜（約 US$20–100/月，quota 制）※需再確認 | 無明列學術方案 |
| **VesselFinder API** | ✅ | ✅ port calls / voyage | ✅ 選配 | ✅ | 中～高（依方案報價） | 無明列 |
| **MarineTraffic API** | ✅ | ✅ Port Calls / Voyage History 端點 | ✅ | ✅ 佳 | 高（credit 制，逐次計費） | ✅ 有學術/研究洽詢窗口 |
| **Spire Maritime** | ✅ | ✅ 完整歷史 | ✅ 原生衛星 | ✅ | 企業級（最貴） | 偶有研究合作 |
| **UN Global Platform / exactEarth 學術** | 依方案 | ✅ | ✅ | ✅ | 研究用途 | ✅ 需申請 |

> 價格與方案會變動，表中級距為概估，實際須各家詢價。credit/quota 制要特別注意：
> 我們是「對每艘抵港船各查一次歷史」，用量 = 抵港船數 × 查詢次數，需估算月用量。

## 三、建議

- **學生預算、要快**：優先評估 **Datalastic** — 有 `vessel_history` / `vessel_pro`（含近期靠港）
  且月費親民，最可能用得起。先用它的免費試用額度打通流程。
- **系所/計畫有資源**：**MarineTraffic**（成熟、Port Calls 端點明確、有學術窗口）或走
  **UN Global Platform AIS** 研究申請（免費但需審核、資料為研究用途）。
- **要衛星級高雄涵蓋且不缺經費**：**Spire**。

## 四、接進系統要改哪裡（工程量很小）

系統的 `AISProvider` 介面就是為了換來源而設計的（分析層完全不用動）。新增一個
「歷史型」provider 即可——**它不需長時間收集**，而是直接查每艘船的歷史靠港：

### 4.1 新增 provider（範例：`DatalasticAISProvider`）

在 `app/sources/ais_provider.py` 加一個類別，實作 `fetch_port_calls()`：

```python
class DatalasticAISProvider(AISProvider):
    source_name = "datalastic"

    def fetch_port_calls(self) -> list[PortCallRecord]:
        # 1) 取目標港（高雄）近期/預計抵港船清單 → 得到一批 MMSI/IMO
        arrivals = self._api_arrivals(settings.target_port_unlocode)
        records = []
        for v in arrivals:
            # 2) 對每艘船查歷史靠港序列（近 track_lookback_days 天）
            for call in self._api_vessel_history(v["mmsi"], settings.track_lookback_days):
                records.append(PortCallRecord(
                    ship_code=str(v["mmsi"]), mmsi=str(v["mmsi"]), imo=v.get("imo"),
                    name=v.get("name"), port_unlocode=_to_unlocode(call["port"]),
                    arrival=call["arrival"], departure=call.get("departure"),
                    source=self.source_name,
                ))
        return records
```

重點：歷史型 API **一次就給完整序列**，所以 `prev_foreign_call()` 立刻有真實的前一外國港，
不再需要 `collect_ais_loop.py` 跑一兩天，也不受陸基涵蓋孤島限制。

### 4.2 設定與路由（各約 1–2 行）

- `app/config.py`：加 `datalastic_api_key`（或對應廠商金鑰）。
- `app/sources/ais_provider.py::get_provider()`：加 `if provider == "datalastic": return DatalasticAISProvider()`。
- `.env`：`AIS_PROVIDER=datalastic`、`DATALASTIC_API_KEY=...`。

### 4.3 需要注意

- **UN/LOCODE 對齊**：各家的港口欄位多為港名/座標，需把它對回本專案的 UN/LOCODE
  （可用 `data/ports_seed.csv` 座標最近鄰，或擴充為 improved-un-locodes 全球表）。
- **配額與快取**：付費多為 credit 制。沿用現有 `data/ais_sightings.json` 或加一層查詢快取，
  避免對同一船重複計費。
- **測試**：`tests/` 用 mock provider，不打網路；新 provider 可加離線 fixture 測 `fetch_port_calls()` 轉換邏輯。

## 五、免費路線能做到的極限（誠實對照）

即使不花錢，現有 aisstream 版本仍有兩個站得住腳的用途：
1. 證明系統能**即時接進大量真實抵港船**（24h 實測 2,000+ 艘真船，見報告圖表）。
2. 用船隻廣播的 **Destination 欄位**觀察「宣告目的地為高雄/基隆」的真實船（雖非航跡歷史）。

要「真船 × 真外國港 × 真疫情 → 真風險分數」，就升級到第二～四節的付費/學術來源；
介面已抽象化，換來源不動分析與 API 層。
