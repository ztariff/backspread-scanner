"""
Polygon.io REST API client for the diagonal ratio backspread scanner.

Handles:
  - Option chain snapshots (multiple expirations)
  - Historical price data for realized volatility
  - Ticker universe discovery
  - Rate limiting, pagination, error recovery
"""

import time
import math
import logging
import requests
from datetime import date, timedelta
from typing import List, Optional, Dict, Any, Tuple

from option_chain import OptionContract, OptionChain

logger = logging.getLogger("backspread_scanner.polygon")


class PolygonAPIError(Exception):
    pass


class PolygonClient:
    """
    Polygon.io API wrapper.

    Usage
    -----
        client = PolygonClient(api_key="...")
        chain = client.get_option_chain("AAPL", "2026-03-20")
        rv = client.get_realized_vol("AAPL", lookback=252)
        max_move = client.get_max_move("AAPL", lookback=252)
    """

    BASE_URL = "https://api.polygon.io"

    def __init__(self, api_key: str, rate_limit_pause: float = 0.25):
        self.api_key = api_key
        self.rate_limit_pause = rate_limit_pause
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})
        self._last_call = 0.0

    # ------------------------------------------------------------------
    # HTTP layer
    # ------------------------------------------------------------------

    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.rate_limit_pause:
            time.sleep(self.rate_limit_pause - elapsed)
        self._last_call = time.time()

    def _get(self, url: str, params: dict = None, max_retries: int = 3) -> dict:
        for attempt in range(max_retries):
            self._throttle()
            try:
                resp = self.session.get(url, params=params, timeout=30)

                if resp.status_code == 429:
                    wait = min(2 ** attempt * 1.0, 30.0)
                    logger.warning(f"Rate limited. Waiting {wait:.1f}s (attempt {attempt+1})")
                    time.sleep(wait)
                    continue

                if resp.status_code == 403:
                    raise PolygonAPIError(
                        "403 Forbidden — check your API key and subscription tier"
                    )

                resp.raise_for_status()
                return resp.json()

            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout (attempt {attempt+1})")
                if attempt == max_retries - 1:
                    raise
            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error (attempt {attempt+1})")
                if attempt == max_retries - 1:
                    raise
                time.sleep(1.0)

        return {}

    # ------------------------------------------------------------------
    # Stock / underlying data
    # ------------------------------------------------------------------

    def get_stock_price(self, ticker: str) -> Optional[float]:
        """Fetch previous-day close for *ticker*."""
        url = f"{self.BASE_URL}/v2/aggs/ticker/{ticker}/prev"
        try:
            data = self._get(url)
            results = data.get("results", [])
            if results:
                return float(results[0].get("c", 0))
        except Exception as e:
            logger.error(f"Failed to fetch price for {ticker}: {e}")
        return None

    def get_historical_prices(
        self, ticker: str, lookback_days: int = 252
    ) -> List[Dict[str, Any]]:
        """
        Fetch daily OHLCV bars for the past *lookback_days* trading days.
        Returns list of dicts with keys: date, open, high, low, close, volume.
        """
        end = date.today()
        start = end - timedelta(days=int(lookback_days * 1.5))  # buffer for weekends

        url = f"{self.BASE_URL}/v2/aggs/ticker/{ticker}/range/1/day/{start.isoformat()}/{end.isoformat()}"
        params = {"adjusted": "true", "sort": "asc", "limit": 5000}

        try:
            data = self._get(url, params)
            results = data.get("results", [])
            bars = []
            for r in results:
                bars.append({
                    "date": r.get("t"),  # unix ms timestamp
                    "open": float(r.get("o", 0)),
                    "high": float(r.get("h", 0)),
                    "low": float(r.get("l", 0)),
                    "close": float(r.get("c", 0)),
                    "volume": int(r.get("v", 0)),
                })
            return bars[-lookback_days:]  # trim to requested lookback
        except Exception as e:
            logger.error(f"Failed to fetch historical prices for {ticker}: {e}")
            return []

    def get_realized_vol(self, ticker: str, lookback: int = 252) -> Optional[float]:
        """
        Calculate annualized realized volatility from daily close-to-close returns.
        """
        bars = self.get_historical_prices(ticker, lookback)
        if len(bars) < 20:
            logger.warning(f"Insufficient history for {ticker} ({len(bars)} bars)")
            return None

        closes = [b["close"] for b in bars if b["close"] > 0]
        if len(closes) < 20:
            return None

        log_returns = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes))]
        mean_ret = sum(log_returns) / len(log_returns)
        variance = sum((r - mean_ret) ** 2 for r in log_returns) / (len(log_returns) - 1)
        daily_vol = math.sqrt(variance)
        annual_vol = daily_vol * math.sqrt(252)
        return annual_vol

    def get_max_moves(self, ticker: str, lookback: int = 252) -> Dict[str, Any]:
        """
        Find the largest up and down moves in the lookback period.
        Returns dict with max_up_pct, max_down_pct, max_up_date, max_down_date,
        avg_daily_range_pct, and a list of significant moves.
        """
        bars = self.get_historical_prices(ticker, lookback)
        if len(bars) < 10:
            return {}

        closes = [b["close"] for b in bars if b["close"] > 0]
        daily_returns = []
        for i in range(1, len(closes)):
            ret = (closes[i] - closes[i-1]) / closes[i-1]
            daily_returns.append(ret)

        if not daily_returns:
            return {}

        max_up = max(daily_returns)
        max_down = min(daily_returns)
        max_up_idx = daily_returns.index(max_up)
        max_down_idx = daily_returns.index(max_down)

        # Multi-day moves (rolling 5-day, 10-day, 20-day)
        multi_day_moves = {}
        for window in [5, 10, 20]:
            if len(closes) > window:
                window_returns = [
                    (closes[i] - closes[i - window]) / closes[i - window]
                    for i in range(window, len(closes))
                ]
                multi_day_moves[f"max_{window}d_up"] = max(window_returns)
                multi_day_moves[f"max_{window}d_down"] = min(window_returns)

        # Daily ranges
        daily_ranges = [(b["high"] - b["low"]) / b["close"] for b in bars if b["close"] > 0]
        avg_range = sum(daily_ranges) / len(daily_ranges) if daily_ranges else 0

        return {
            "max_up_pct": max_up,
            "max_down_pct": max_down,
            "avg_daily_range_pct": avg_range,
            "current_price": closes[-1] if closes else 0,
            **multi_day_moves,
        }

    # ------------------------------------------------------------------
    # Option chain
    # ------------------------------------------------------------------

    def get_option_chain(
        self,
        ticker: str,
        expiration_date: str,
        underlying_price: Optional[float] = None,
    ) -> OptionChain:
        """Fetch full option chain for ticker at a single expiration."""
        if underlying_price is None:
            underlying_price = self.get_stock_price(ticker) or 0.0

        chain = OptionChain(
            ticker=ticker,
            expiration=expiration_date,
            underlying_price=underlying_price,
        )

        contracts = self._fetch_option_contracts(ticker, expiration_date)

        for c in contracts:
            opt = self._parse_contract(c, ticker, expiration_date)
            if opt is None:
                continue
            if opt.option_type == "call":
                chain.calls.append(opt)
            else:
                chain.puts.append(opt)

        chain.sort_by_strike()
        logger.info(
            f"Fetched chain: {ticker} exp={expiration_date} "
            f"({len(chain.calls)}C / {len(chain.puts)}P)"
        )
        return chain

    def get_multi_expiry_chains(
        self,
        ticker: str,
        short_expirations: List[str],
        long_expirations: List[str],
        underlying_price: Optional[float] = None,
    ) -> Dict[str, OptionChain]:
        """
        Fetch chains for multiple expirations efficiently.
        Returns dict keyed by expiration date string.
        """
        if underlying_price is None:
            underlying_price = self.get_stock_price(ticker) or 0.0

        chains = {}
        all_exps = set(short_expirations + long_expirations)

        for exp in sorted(all_exps):
            try:
                chain = self.get_option_chain(ticker, exp, underlying_price)
                chains[exp] = chain
            except Exception as e:
                logger.warning(f"Failed to fetch chain {ticker} exp={exp}: {e}")

        return chains

    def _fetch_option_contracts(
        self, ticker: str, expiration_date: str
    ) -> List[dict]:
        """Paginated fetch of option contracts from snapshot endpoint."""
        all_results = []

        url = f"{self.BASE_URL}/v3/snapshot/options/{ticker}"
        params = {"expiration_date": expiration_date, "limit": 250}

        try:
            data = self._get(url, params)
            results = data.get("results", [])
            all_results.extend(results)

            next_url = data.get("next_url")
            while next_url:
                if "apiKey" not in next_url and "api_key" not in next_url:
                    sep = "&" if "?" in next_url else "?"
                    next_url = f"{next_url}{sep}apiKey={self.api_key}"
                data = self._get(next_url)
                results = data.get("results", [])
                all_results.extend(results)
                next_url = data.get("next_url")

        except PolygonAPIError:
            raise
        except Exception as e:
            logger.warning(f"Snapshot failed for {ticker}, trying contracts endpoint: {e}")
            all_results = self._fetch_contracts_list(ticker, expiration_date)

        return all_results

    def _fetch_contracts_list(
        self, ticker: str, expiration_date: str
    ) -> List[dict]:
        """Fallback: list contracts + individual quotes."""
        url = f"{self.BASE_URL}/v3/reference/options/contracts"
        params = {
            "underlying_ticker": ticker,
            "expiration_date": expiration_date,
            "limit": 250,
            "sort": "strike_price",
        }

        all_contracts = []
        try:
            data = self._get(url, params)
            for contract in data.get("results", []):
                contract_ticker = contract.get("ticker", "")
                quote = self._get_option_quote(contract_ticker)
                if quote:
                    contract["_quote"] = quote
                all_contracts.append(contract)

            next_url = data.get("next_url")
            while next_url:
                data = self._get(next_url)
                for contract in data.get("results", []):
                    contract_ticker = contract.get("ticker", "")
                    quote = self._get_option_quote(contract_ticker)
                    if quote:
                        contract["_quote"] = quote
                    all_contracts.append(contract)
                next_url = data.get("next_url")

        except Exception as e:
            logger.error(f"Failed to fetch contracts for {ticker}: {e}")

        return all_contracts

    def _get_option_quote(self, option_ticker: str) -> Optional[dict]:
        url = f"{self.BASE_URL}/v3/quotes/{option_ticker}"
        params = {"limit": 1, "sort": "timestamp", "order": "desc"}
        try:
            data = self._get(url, params)
            results = data.get("results", [])
            return results[0] if results else None
        except Exception:
            return None

    def _parse_contract(
        self, raw: dict, ticker: str, expiration_date: str
    ) -> Optional[OptionContract]:
        """Parse Polygon response into OptionContract."""
        try:
            details = raw.get("details", {})
            day = raw.get("day", {})
            last_quote = raw.get("last_quote", {})
            greeks = raw.get("greeks", {})

            if details:
                strike = float(details.get("strike_price", 0))
                opt_type = details.get("contract_type", "").lower()
                contract_symbol = details.get("ticker", "")
                exp = details.get("expiration_date", expiration_date)

                bid = float(last_quote.get("bid", 0) or 0)
                ask = float(last_quote.get("ask", 0) or 0)
                last_price = float(
                    day.get("close", 0) or last_quote.get("midpoint", 0) or 0
                )
                volume = int(day.get("volume", 0) or 0)
                oi = int(raw.get("open_interest", 0) or 0)
                iv = greeks.get("implied_volatility")
                if iv is not None:
                    iv = float(iv)

                opt_delta = greeks.get("delta")
                opt_gamma = greeks.get("gamma")
                opt_vega = greeks.get("vega")
                opt_theta = greeks.get("theta")
            else:
                strike = float(raw.get("strike_price", 0))
                opt_type = raw.get("contract_type", "").lower()
                contract_symbol = raw.get("ticker", "")
                exp = raw.get("expiration_date", expiration_date)

                quote = raw.get("_quote", {})
                bid = float(quote.get("bid_price", 0) or 0)
                ask = float(quote.get("ask_price", 0) or 0)
                last_price = float(quote.get("midpoint", 0) or 0)
                volume = 0
                oi = 0
                iv = None
                opt_delta = None
                opt_gamma = None
                opt_vega = None
                opt_theta = None

            if strike <= 0 or opt_type not in ("call", "put"):
                return None

            return OptionContract(
                ticker=ticker,
                strike=strike,
                expiration=exp,
                option_type=opt_type,
                bid=bid,
                ask=ask,
                last=last_price,
                volume=volume,
                open_interest=oi,
                implied_volatility=iv,
                contract_symbol=contract_symbol,
                delta=float(opt_delta) if opt_delta is not None else None,
                gamma=float(opt_gamma) if opt_gamma is not None else None,
                vega=float(opt_vega) if opt_vega is not None else None,
                theta=float(opt_theta) if opt_theta is not None else None,
            )

        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Failed to parse contract: {e}")
            return None

    # ------------------------------------------------------------------
    # Expiration dates
    # ------------------------------------------------------------------

    def get_expirations(
        self, ticker: str, min_dte: int = 0, max_dte: int = 365
    ) -> List[str]:
        """
        List available option expiration dates for *ticker*,
        filtered by DTE range.
        """
        url = f"{self.BASE_URL}/v3/reference/options/contracts"
        params = {
            "underlying_ticker": ticker,
            "limit": 1000,
            "sort": "expiration_date",
        }
        expirations = set()
        try:
            data = self._get(url, params)
            today = date.today()
            for c in data.get("results", []):
                exp = c.get("expiration_date")
                if exp:
                    try:
                        exp_date = date.fromisoformat(exp)
                        dte = (exp_date - today).days
                        if min_dte <= dte <= max_dte:
                            expirations.add(exp)
                    except ValueError:
                        pass
        except Exception as e:
            logger.error(f"Failed to get expirations for {ticker}: {e}")
        return sorted(expirations)

    # ------------------------------------------------------------------
    # Universe discovery
    # ------------------------------------------------------------------

    def get_sp500_tickers(self) -> List[str]:
        """
        Fetch a list of active US equity tickers from Polygon.
        Filters for common stocks with options.
        Note: This returns a broad list, not strictly S&P 500.
        """
        url = f"{self.BASE_URL}/v3/reference/tickers"
        params = {
            "market": "stocks",
            "active": "true",
            "type": "CS",  # common stock
            "locale": "us",
            "limit": 1000,
            "sort": "ticker",
        }

        tickers = []
        try:
            data = self._get(url, params)
            for t in data.get("results", []):
                ticker = t.get("ticker", "")
                if ticker and len(ticker) <= 5 and ticker.isalpha():
                    tickers.append(ticker)

            # Paginate
            next_url = data.get("next_url")
            while next_url and len(tickers) < 3000:
                data = self._get(next_url)
                for t in data.get("results", []):
                    ticker = t.get("ticker", "")
                    if ticker and len(ticker) <= 5 and ticker.isalpha():
                        tickers.append(ticker)
                next_url = data.get("next_url")

        except Exception as e:
            logger.error(f"Failed to fetch ticker universe: {e}")

        return tickers

    def get_index_and_etf_tickers(self) -> List[str]:
        """
        Return a curated list of major indices, ETFs, and commodity ETFs
        that have liquid options markets.
        """
        return [
            # Major indices
            "SPY", "QQQ", "IWM", "DIA",
            # Sector ETFs
            "XLF", "XLE", "XLK", "XLV", "XLU", "XLI", "XLP", "XLB", "XLRE", "XLC",
            # Volatility
            "VXX", "UVXY", "SVXY",
            # Bonds / Rates
            "TLT", "IEF", "SHY", "HYG", "LQD", "TBT",
            # Commodities
            "GLD", "SLV", "USO", "UNG", "GDX", "GDXJ",
            # International
            "EEM", "FXI", "EWZ", "EWJ",
            # Large caps with liquid options
            "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA",
            "AMD", "NFLX", "CRM", "COIN", "MARA", "RIOT",
            # Meme / high vol
            "GME", "AMC",
            # Leveraged
            "TQQQ", "SQQQ", "SPXU", "SPXL",
        ]
