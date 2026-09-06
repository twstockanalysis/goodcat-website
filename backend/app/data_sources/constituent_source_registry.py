"""Official ETF constituent-source coverage for every TWSE-listed issuer."""

from dataclasses import dataclass
from enum import StrEnum


class ConstituentSourceStatus(StrEnum):
    AUTOMATED = "AUTOMATED"
    FULL_DISCLOSURE_VERIFIED = "FULL_DISCLOSURE_VERIFIED"
    ENTRYPOINT_VERIFIED = "ENTRYPOINT_VERIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class ConstituentSource:
    issuer_key: str
    issuer_name: str
    representative_etf_code: str
    official_url: str
    status: ConstituentSourceStatus
    locator: str
    note: str


CONSTITUENT_SOURCES: dict[str, ConstituentSource] = {
    "yuanta": ConstituentSource(
        "yuanta", "元大", "0050",
        "https://www.yuantaetfs.com/product/detail/0050/ratio",
        ConstituentSourceStatus.AUTOMATED, "ETF_CODE_IN_PATH",
        "Complete PCF/Daily stock weights are imported by the active adapter.",
    ),
    "fubon": ConstituentSource(
        "fubon", "富邦", "006208",
        "https://websys.fsit.com.tw/FubonETF/Trade/Pcf.aspx?lan=TW&stkId=006208",
        ConstituentSourceStatus.AUTOMATED,
        "ETF_CODE_QUERY", "Official PCF assets are imported by the active adapter.",
    ),
    "sinopac": ConstituentSource(
        "sinopac", "永豐", "00930",
        "https://sitc.sinopac.com/SinopacEtfs/Etfs/Pcf/00930",
        ConstituentSourceStatus.AUTOMATED,
        "ETF_CODE_IN_PATH", "Official PCF stock weights are imported by the active adapter.",
    ),
    "mega": ConstituentSource(
        "mega", "兆豐", "00932",
        "https://www.megafunds.com.tw/MEGA/etf/etf_product.aspx?id=19",
        ConstituentSourceStatus.AUTOMATED,
        "INTERNAL_FUND_ID", "Official catalog mapping and holdings are imported.",
    ),
    "cathay": ConstituentSource(
        "cathay", "國泰", "00878",
        "https://www.cathaysite.com.tw/ETF/detail/ECN?tab=etf3",
        ConstituentSourceStatus.AUTOMATED,
        "INTERNAL_FUND_CODE", "Official catalog resolves API fund code independently of page route.",
    ),
    "first": ConstituentSource(
        "first", "第一金", "00408A",
        "https://www.fsitc.com.tw/FundDetail.aspx?ID=183",
        ConstituentSourceStatus.AUTOMATED,
        "INTERNAL_FUND_ID", "Official ETF catalog and reconciled asset weights are imported.",
    ),
    "fuh_hwa": ConstituentSource(
        "fuh_hwa", "復華", "00929",
        "https://www.fhtrust.com.tw/ETF/etf_detail/ETF21",
        ConstituentSourceStatus.AUTOMATED,
        "INTERNAL_FUND_ID", "Official catalog mapping and asset Excel are imported.",
    ),
    "capital": ConstituentSource(
        "capital", "群益", "00923",
        "https://www.capitalfund.com.tw/etf/product/detail/365/buyback",
        ConstituentSourceStatus.AUTOMATED,
        "INTERNAL_FUND_ID", "Official catalog, fund identity and complete buyback API are imported.",
    ),
    "taishin": ConstituentSource(
        "taishin", "台新", "00987A",
        "https://www.tsit.com.tw/ETF/Home/ETFSeriesDetail/00987A",
        ConstituentSourceStatus.AUTOMATED,
        "ETF_CODE_IN_PATH", "Official holdings are imported by the active adapter.",
    ),
    "ctbc": ConstituentSource(
        "ctbc", "中國信託", "00891",
        "https://www.ctbcinvestments.com.tw/CTWEB/Content/ETF/pcd.aspx?ETF_ID=00891",
        ConstituentSourceStatus.AUTOMATED,
        "ETF_CODE_QUERY", "Official PCF stock weights are imported by the active adapter.",
    ),
    "upam": ConstituentSource(
        "upam", "統一", "00939",
        "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=46YTW",
        ConstituentSourceStatus.AUTOMATED,
        "INTERNAL_FUND_CODE", "Official catalog mapping and embedded asset holdings are imported.",
    ),
    "jko": ConstituentSource(
        "jko", "街口", "00693U",
        "https://ec.jkoam.com/EventArea/classroom.php",
        ConstituentSourceStatus.NOT_APPLICABLE,
        "FUTURES_ETF_ONLY",
        "Current TWSE products are commodity futures trusts, not equity portfolios.",
    ),
    "franklin": ConstituentSource(
        "franklin", "富蘭克林", "00905",
        "https://www.ftft.com.tw/etf/product/details/?id=131&tab=profile",
        ConstituentSourceStatus.AUTOMATED,
        "INTERNAL_FUND_ID", "Official ETF catalog and holdings API are imported.",
    ),
    "kgi": ConstituentSource(
        "kgi", "凱基", "00915",
        "https://www.kgifund.com.tw/Fund/Detail?fundID=J015",
        ConstituentSourceStatus.AUTOMATED,
        "INTERNAL_FUND_ID", "Official catalog discovery and complete holdings table are imported.",
    ),
    "uob": ConstituentSource(
        "uob", "大華銀", "00918",
        "https://www.uobam.com.tw/fund/etf/pcf?fundID=88281125",
        ConstituentSourceStatus.AUTOMATED,
        "INTERNAL_FUND_ID", "Official event mapping and PCF holdings are imported.",
    ),
    "nomura": ConstituentSource(
        "nomura", "野村", "00944",
        "https://www.nomurafunds.com.tw/ETFWEB/pcf",
        ConstituentSourceStatus.AUTOMATED,
        "ETF_CODE_BODY",
        "Official GetFundAssets holdings are imported by the active adapter.",
    ),
    "esun": ConstituentSource(
        "esun", "玉山", "009803",
        "https://www.esunam.com/ETF/etf-pcf",
        ConstituentSourceStatus.AUTOMATED,
        "INTERNAL_FUND_ID",
        "Official overview mapping and GetFundAssets holdings are imported.",
    ),
    "union": ConstituentSource(
        "union", "聯邦", "009804",
        "https://www.usitc.com.tw/CustCenter/BuyBackList",
        ConstituentSourceStatus.AUTOMATED,
        "FORM_SELECTION",
        "Official form discovery and complete holdings are imported.",
    ),
    "hnh": ConstituentSource(
        "hnh", "華南永昌", "009808",
        "https://www.hnfunds.com.tw/WEB_API/HN_OW_PROD/swagger/index.html",
        ConstituentSourceStatus.AUTOMATED,
        "ETFID_QUERY_WITH_SYSTEM_TOKEN",
        "Official short-lived public token and PCF holdings are imported.",
    ),
    "allianz": ConstituentSource(
        "allianz", "安聯", "00984A",
        "https://etf.allianzgi.com.tw/etf-info/E0001?tab=4",
        ConstituentSourceStatus.AUTOMATED,
        "ANTIFORGERY_INTERNAL_FUND_ID",
        "Official antiforgery session, overview mapping and holdings are imported.",
    ),
    "blackrock": ConstituentSource(
        "blackrock", "貝萊德投信", "009813",
        "https://www.blackrock.com/tw/products/345655/blackrock-ishares-s-p-500-top-50-etf",
        ConstituentSourceStatus.FULL_DISCLOSURE_VERIFIED,
        "INTERNAL_PRODUCT_ID",
        "Complete holdings were verified, but official page and CSV automation are access-protected.",
    ),
    "jpmorgan": ConstituentSource(
        "jpmorgan", "摩根", "00989A",
        "https://am.jpmorgan.com/tw/zh/asset-management/twetf/products/jpmorgan-taiwan-us-tech-leaders-active-etf-tw00000989a5",
        ConstituentSourceStatus.AUTOMATED,
        "ISIN_SLUG",
        "Official autocomplete mapping and product-data PCF holdings are imported.",
    ),
    "alliancebernstein": ConstituentSource(
        "alliancebernstein", "聯博", "00404A",
        "https://www.abfunds.com.tw/zh-tw/etfs/pcf.TW00000404A5.html",
        ConstituentSourceStatus.AUTOMATED,
        "ISIN_PATH",
        "Official ETF catalog mapping and reconciled equity holdings are imported.",
    ),
}


def get_constituent_source(issuer_key: str) -> ConstituentSource:
    normalized = issuer_key.strip().lower()
    try:
        return CONSTITUENT_SOURCES[normalized]
    except KeyError as error:
        raise KeyError(f"找不到 ETF 成分股來源：{normalized}") from error
