"""Bounded Cathay TWD fund-size acquisition through existing official APIs."""

from datetime import date, datetime, timezone
from decimal import Decimal
import json
import re
from urllib.parse import urlencode

import httpx

from backend.app.data_sources.cathay_constituent_adapter import API_BASE, _get
from backend.app.models.fund_size import FundSizeEvidence


def parse_cathay_fund_size(code, fund_code, catalog_row, identity, assets, *,
                           evaluated_on, fetched_at):
    for row in (catalog_row, identity):
        if not isinstance(row, dict) or row.get("stockCode") != code or row.get("fundCode") != fund_code:
            raise ValueError("Cathay ETF identity mismatch")
    if identity.get("currency") != "新台幣":
        raise ValueError("Explicit TWD fund currency required")
    if not isinstance(assets, dict):
        raise ValueError("Cathay fund assets unavailable")
    effective = date.fromisoformat(str(assets.get("preDate", "")).replace("/", "-"))
    if not 0 <= (evaluated_on - effective).days <= 7:
        raise ValueError("Cathay asset date future or stale")
    raw = str(assets.get("fundNav", "")).strip()
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?", raw):
        raise ValueError("Invalid reported total fund net assets")
    return FundSizeEvidence(
        etf_code=code, fund_code=fund_code, as_of_date=effective,
        fetched_at=fetched_at, total_net_assets_twd=Decimal(raw.replace(",", "")),
        source_url=API_BASE + "GetETFAssets?" + urlencode({
            "FundCode": fund_code, "SearchDate": effective.isoformat(), "status": 1}),
        evidence_json=json.dumps({"catalog_row": catalog_row, "identity": identity,
                                  "assets": assets}, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")),
    )


def fetch_cathay_fund_size(etf_code, *, evaluated_on: date, snapshot_on: date | None = None,
                          allow_network=False, client=None):
    if not allow_network:
        raise ValueError("Network acquisition requires allow_network=True")
    code = etf_code.strip().upper()
    if not re.fullmatch(r"[0-9A-Z]{4,10}", code):
        raise ValueError("Invalid ETF code")
    requested = snapshot_on or evaluated_on
    if not 0 <= (evaluated_on - requested).days <= 7:
        raise ValueError("Requested snapshot future or stale")
    if client is None:
        with httpx.Client(timeout=30, follow_redirects=False) as owned:
            return fetch_cathay_fund_size(code, evaluated_on=evaluated_on,
                                          snapshot_on=requested, allow_network=True, client=owned)
    catalog = _get(client, "GetETFDetailPriceList", Keyword="", orderBy=0, orderType=2)
    if not isinstance(catalog, list):
        raise ValueError("Cathay catalog unavailable")
    matches = [row for row in catalog if isinstance(row, dict) and row.get("stockCode") == code]
    if len(matches) != 1:
        raise ValueError("Cathay catalog identity unavailable or ambiguous")
    fund = matches[0].get("fundCode", "")
    if not isinstance(fund, str) or not re.fullmatch(r"[A-Z0-9]{1,10}", fund):
        raise ValueError("Invalid Cathay fund code")
    identity = _get(client, "GetETFInfoMain", FundCode=fund)
    assets = _get(client, "GetETFAssets", FundCode=fund, SearchDate=requested.isoformat())
    result = parse_cathay_fund_size(code, fund, matches[0], identity, assets,
                                   evaluated_on=evaluated_on, fetched_at=datetime.now(timezone.utc))
    if result.as_of_date != requested:
        raise ValueError("Requested and returned snapshot date differ")
    return result
