"""Cathay official stock snapshots, resolved through the public ETF catalog."""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import re
from zoneinfo import ZoneInfo

import httpx

from backend.app.models.etf_constituent import ETFConstituentSnapshotCreate

API_BASE = "https://cwapi.cathaysite.com.tw/api/ETF/"
SOURCE_ID = "cathay_official_stock_list"


def _get(client, endpoint, **params):
    with client.stream("GET", API_BASE + endpoint, params={**params, "status": 1}) as response:
        response.raise_for_status()
        content = bytearray()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > 5_000_000:
                raise ValueError("Cathay response exceeds size limit")
    payload = json.loads(content)
    if not isinstance(payload, dict) or payload.get("returnCode") != "2000":
        raise ValueError("Cathay official response unavailable")
    return payload.get("result")


def parse_cathay_snapshot(code, fund_code, identity, assets, stocks, *, evaluated_on, fetched_at):
    if not isinstance(identity, dict) or identity.get("stockCode") != code or identity.get("fundCode") != fund_code:
        raise ValueError("Cathay ETF identity mismatch")
    if not isinstance(assets, dict):
        raise ValueError("Cathay asset date unavailable")
    as_of = date.fromisoformat(str(assets.get("preDate", "")).replace("/", "-"))
    if as_of > evaluated_on or (evaluated_on - as_of).days > 7:
        raise ValueError("Cathay asset date future or stale")
    if not isinstance(stocks, list) or not stocks:
        raise ValueError("Cathay direct stock list unavailable")
    positions = []
    for rank, row in enumerate(stocks, 1):
        if not isinstance(row, dict):
            raise ValueError("Cathay stock row invalid")
        try:
            weight = Decimal(str(row.get("weights", "")))
        except InvalidOperation as error:
            raise ValueError("Cathay stock weight invalid") from error
        if not weight.is_finite() or weight < 0:
            raise ValueError("Cathay stock weight invalid")
        if weight == 0:
            continue
        name = str(row.get("stockName", ""))
        if re.search(r"\b(?:ETF|ETN|FUTURES?|UCITS)\b|指數型基金|期貨", name, re.IGNORECASE):
            raise ValueError("Cathay nested ETF or derivative is not direct stock evidence")
        positions.append(dict(
            constituent_id=row.get("stockCode", ""),
            constituent_name=name,
            weight_pct=weight, rank=rank,
        ))
    if sum((p["weight_pct"] for p in positions), Decimal("0")) < 90:
        raise ValueError("Cathay direct stock coverage below 90 percent")
    return ETFConstituentSnapshotCreate(
        etf_code=code, as_of_date=as_of, source_id=SOURCE_ID,
        source_url=f"https://www.cathaysite.com.tw/ETF/detail/E{fund_code}?tab=etf3",
        fetched_at=fetched_at, positions=positions,
    )


def fetch_cathay_constituent_snapshot(etf_code, *, evaluated_on=None, client=None):
    code = etf_code.strip().upper()
    if not re.fullmatch(r"[0-9A-Z]{4,10}", code):
        raise ValueError("Invalid ETF code")
    today = evaluated_on or datetime.now(ZoneInfo("Asia/Taipei")).date()
    if client is None:
        with httpx.Client(timeout=30, follow_redirects=False, headers={
            "lang": "zh_TW", "User-Agent": "GoodCat/0.1 (official-data-downloader)",
        }) as owned:
            return fetch_cathay_constituent_snapshot(code, evaluated_on=today, client=owned)
    catalog = _get(client, "GetETFDetailPriceList", Keyword="", orderBy=0, orderType=2)
    if not isinstance(catalog, list):
        raise ValueError("Cathay catalog unavailable")
    matches = [row for row in catalog if isinstance(row, dict) and row.get("stockCode") == code]
    if len(matches) != 1:
        raise ValueError("Cathay catalog identity unavailable or ambiguous")
    fund = matches[0].get("fundCode", "")
    if not re.fullmatch(r"[A-Z0-9]{1,10}", fund):
        raise ValueError("Cathay fund code invalid")
    identity = _get(client, "GetETFInfoMain", FundCode=fund)
    assets = _get(client, "GetETFAssets", FundCode=fund, SearchDate="")
    # An empty date selects the latest disclosure, including on weekends.
    # Request stock rows for that date, never stamp today's date onto them.
    if not isinstance(assets, dict):
        raise ValueError("Cathay assets unavailable")
    effective = date.fromisoformat(str(assets.get("preDate", "")).replace("/", "-"))
    if effective > today or (today - effective).days > 7:
        raise ValueError("Cathay asset date future or stale")
    stocks = _get(client, "GetETFDetailStockList", FundCode=fund, SearchDate=effective.isoformat())
    return parse_cathay_snapshot(code, fund, identity, assets, stocks,
        evaluated_on=today, fetched_at=datetime.now(timezone.utc))
