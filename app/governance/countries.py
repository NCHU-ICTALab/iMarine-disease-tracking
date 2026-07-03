"""國名 → ISO3166-1 alpha-2 對照（治理層，供 WHO/新聞的文字地名標準化）。

疾管署 CSV 已直接提供 ISO 碼，此表主要供 WHO DON 的 Title 地名與新聞使用。
僅收錄海運/疫情相關的常見國別；未命中時回傳 None，由上層決定是否保留為純文字。
"""
from __future__ import annotations

# 主要維護：小寫國名（含常見變體）-> ISO2
_NAME_TO_ISO2: dict[str, str] = {
    "taiwan": "TW", "china": "CN", "people's republic of china": "CN",
    "hong kong": "HK", "singapore": "SG", "korea": "KR",
    "republic of korea": "KR", "south korea": "KR", "japan": "JP",
    "philippines": "PH", "vietnam": "VN", "viet nam": "VN",
    "thailand": "TH", "malaysia": "MY", "indonesia": "ID",
    "india": "IN", "united arab emirates": "AE",
    "netherlands": "NL", "united states": "US", "united states of america": "US",
    "sri lanka": "LK", "bangladesh": "BD", "pakistan": "PK",
    "uganda": "UG", "democratic republic of the congo": "CD",
    "congo": "CG", "nigeria": "NG", "ethiopia": "ET", "kenya": "KE",
    "saudi arabia": "SA", "iran": "IR", "iraq": "IQ",
    "laos": "LA", "lao people's democratic republic": "LA",
    "cambodia": "KH", "myanmar": "MM", "brazil": "BR", "peru": "PE",
    "mexico": "MX", "sudan": "SD", "south sudan": "SS", "chad": "TD",
    "ghana": "GH", "guinea": "GN", "liberia": "LR", "sierra leone": "SL",
    "yemen": "YE", "somalia": "SO", "angola": "AO", "tanzania": "TZ",
    "united republic of tanzania": "TZ", "mozambique": "MZ",
    "australia": "AU", "united kingdom": "GB", "france": "FR",
    "germany": "DE", "spain": "ES", "italy": "IT", "egypt": "EG",
}


def resolve_iso2(name: str | None) -> str | None:
    """把地名字串解析為 ISO2；支援「A & B」「A, B」時取第一個可解析者。"""
    if not name:
        return None
    cleaned = name.strip().lower()
    if cleaned in _NAME_TO_ISO2:
        return _NAME_TO_ISO2[cleaned]

    # 拆解多國描述（如 "... Congo & Uganda"），逐段嘗試
    for sep in (" & ", ",", " and "):
        if sep in cleaned:
            for part in cleaned.split(sep):
                iso = _NAME_TO_ISO2.get(part.strip())
                if iso:
                    return iso

    # 子字串比對（如 "Democratic Republic of the Congo (region X)"）
    for key, iso in _NAME_TO_ISO2.items():
        if key in cleaned:
            return iso
    return None
