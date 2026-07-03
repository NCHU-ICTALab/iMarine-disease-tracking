"""資料來源探測：實際打疾管署 CSV 與 WHO DON API，印出欄位與樣本。

用途：在寫 parser 前確認真實資料形狀（欄位名、編碼、日期格式）。
執行：python scripts/probe_sources.py
"""
from __future__ import annotations

import csv
import io
import sys

import httpx

CDC_CSV = (
    "https://www.cdc.gov.tw/CountryEpidLevel/ExportCSV"
    "?type=0&fileName=TCDCTravelAlertAll.csv"
)
WHO_DON = "https://www.who.int/api/news/diseaseoutbreaknews"


def _out(s: str) -> None:
    sys.stdout.buffer.write((s + "\n").encode("utf-8"))


def probe_cdc() -> None:
    _out("===== 疾管署 國際旅遊疫情建議等級表 CSV =====")
    try:
        r = httpx.get(CDC_CSV, timeout=30, verify=False, follow_redirects=True)
        _out(f"HTTP {r.status_code}  bytes={len(r.content)}")
        # 嘗試編碼
        text = None
        for enc in ("utf-8-sig", "utf-8", "big5", "cp950"):
            try:
                text = r.content.decode(enc)
                _out(f"decoded with: {enc}")
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            _out("!! 無法解碼")
            return
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        _out(f"total rows (含 header) = {len(rows)}")
        if rows:
            _out("HEADER: " + " | ".join(rows[0]))
            for row in rows[1:4]:
                _out("ROW   : " + " | ".join(row))
    except Exception as e:  # noqa: BLE001
        _out(f"!! CDC 探測失敗: {e!r}")


def probe_who() -> None:
    _out("\n===== WHO Disease Outbreak News (OData) =====")
    try:
        r = httpx.get(
            WHO_DON,
            params={"$orderby": "PublicationDate desc", "$top": 3},
            timeout=30,
            follow_redirects=True,
        )
        _out(f"HTTP {r.status_code}")
        data = r.json()
        items = data.get("value", [])
        _out(f"returned items = {len(items)}")
        if items:
            _out("KEYS: " + ", ".join(sorted(items[0].keys())))
            for it in items:
                _out(
                    f"- {it.get('DonId')} | {it.get('PublicationDate')} | "
                    f"{(it.get('Title') or '')[:80]}"
                )
    except Exception as e:  # noqa: BLE001
        _out(f"!! WHO 探測失敗: {e!r}")


if __name__ == "__main__":
    probe_cdc()
    probe_who()
