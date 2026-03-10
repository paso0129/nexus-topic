"""
Fetch real-time financial data from free APIs.

Injects accurate market data into article generation prompts
to prevent LLMs from using stale training data.

Sources:
- Exchange rates: exchangerate-api.com (open, no key)
- Stock indices & commodities: Yahoo Finance (yfinance)
- Crypto: CoinGecko public API (no key)
"""

import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 5  # seconds per API call


def _fetch_exchange_rates() -> dict:
    """Fetch USD/KRW, EUR/KRW, JPY/KRW from exchangerate-api.com (free, no key)."""
    try:
        resp = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        rates = resp.json().get("rates", {})

        krw = rates.get("KRW")
        if not krw:
            return {}

        eur_usd = rates.get("EUR")
        jpy_usd = rates.get("JPY")

        result = {"USD/KRW": f"{krw:,.1f}원"}

        if eur_usd:
            eur_krw = krw / eur_usd
            result["EUR/KRW"] = f"{eur_krw:,.1f}원"

        if jpy_usd:
            jpy100_krw = (krw / jpy_usd) * 100
            result["JPY100/KRW"] = f"{jpy100_krw:,.1f}원"

        return result
    except Exception as e:
        logger.warning(f"Exchange rate fetch failed: {e}")
        return {}


def _fetch_indices_and_commodities() -> tuple[dict, dict]:
    """Fetch stock indices and commodities from Yahoo Finance."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed, skipping indices/commodities")
        return {}, {}

    symbols = {
        # Indices
        "^KS11": "코스피",
        "^KQ11": "코스닥",
        "^IXIC": "나스닥",
        "^GSPC": "S&P500",
        # Commodities
        "CL=F": "WTI유",
        "GC=F": "금",
    }

    indices = {}
    commodities = {}

    try:
        tickers = yf.Tickers(" ".join(symbols.keys()))
        for symbol, name in symbols.items():
            try:
                ticker = tickers.tickers[symbol]
                info = ticker.fast_info
                price = info.last_price
                prev_close = info.previous_close

                if not price or not prev_close:
                    continue

                change_pct = ((price - prev_close) / prev_close) * 100
                sign = "+" if change_pct >= 0 else ""

                if symbol in ("CL=F", "GC=F"):
                    commodities[name] = f"${price:,.2f} ({sign}{change_pct:.1f}%)"
                else:
                    indices[name] = f"{price:,.2f} ({sign}{change_pct:.1f}%)"
            except Exception as e:
                logger.warning(f"Failed to fetch {name} ({symbol}): {e}")
    except Exception as e:
        logger.warning(f"Yahoo Finance batch fetch failed: {e}")

    return indices, commodities


def _fetch_crypto() -> dict:
    """Fetch Bitcoin price from CoinGecko public API (no key needed)."""
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd,krw"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json().get("bitcoin", {})

        usd = data.get("usd")
        krw = data.get("krw")
        if usd and krw:
            return {"비트코인": f"${usd:,.0f} (₩{krw:,.0f})"}
        return {}
    except Exception as e:
        logger.warning(f"CoinGecko fetch failed: {e}")
        return {}


def fetch_financial_data() -> dict:
    """
    Fetch all financial data and return a structured dict.

    Returns empty sub-dicts for any failed API calls (fail-safe).
    Total execution target: <10 seconds.
    """
    logger.info("Fetching real-time financial data...")

    exchange_rates = _fetch_exchange_rates()
    indices, commodities = _fetch_indices_and_commodities()
    crypto = _fetch_crypto()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M KST")

    result = {
        "exchange_rates": exchange_rates,
        "indices": indices,
        "commodities": commodities,
        "crypto": crypto,
        "timestamp": timestamp,
    }

    # Count how many data points we got
    total = sum(len(v) for v in [exchange_rates, indices, commodities, crypto])
    logger.info(f"Financial data fetched: {total} data points at {timestamp}")

    return result


def format_financial_context(data: dict) -> str:
    """Format financial data dict into a prompt-injectable text block."""
    if not data:
        return ""

    parts = []

    if data.get("exchange_rates"):
        lines = [f"  - {k}: {v}" for k, v in data["exchange_rates"].items()]
        parts.append("환율:\n" + "\n".join(lines))

    if data.get("indices"):
        lines = [f"  - {k}: {v}" for k, v in data["indices"].items()]
        parts.append("주가지수:\n" + "\n".join(lines))

    if data.get("commodities"):
        lines = [f"  - {k}: {v}" for k, v in data["commodities"].items()]
        parts.append("원자재:\n" + "\n".join(lines))

    if data.get("crypto"):
        lines = [f"  - {k}: {v}" for k, v in data["crypto"].items()]
        parts.append("암호화폐:\n" + "\n".join(lines))

    if not parts:
        return ""

    timestamp = data.get("timestamp", "")

    return f"""
실시간 금융 데이터 ({timestamp} 기준, 반드시 이 수치를 사용하세요):
{chr(10).join(parts)}

중요: 위 데이터는 실시간으로 수집된 정확한 수치입니다.
기사에서 환율, 주가, 원자재 가격을 언급할 때 반드시 이 수치를 기준으로 작성하세요.
학습 데이터의 오래된 수치를 사용하지 마세요.
"""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = fetch_financial_data()
    print(format_financial_context(data))
