"""
Volatility skew analysis for identifying backspread opportunities.

Skew is the key signal: when OTM options carry elevated IV relative to ATM,
selling them (short leg) while buying ATM/ITM options (long leg) creates
a favorable risk/reward through the backspread structure.
"""

import logging
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

from option_chain import OptionChain, OptionContract
from greeks_calculator import BlackScholesCalculator, implied_volatility
from utils import years_to_expiry

logger = logging.getLogger("backspread_scanner.skew")


@dataclass
class SkewMetrics:
    """Container for skew analysis results."""

    ticker: str
    expiration: str
    underlying_price: float

    # ATM reference
    atm_strike: float
    atm_call_iv: Optional[float] = None
    atm_put_iv: Optional[float] = None

    # Put skew (25-delta)
    put_25d_strike: Optional[float] = None
    put_25d_iv: Optional[float] = None
    put_skew_absolute: Optional[float] = None   # 25d_IV - ATM_IV
    put_skew_relative: Optional[float] = None    # (25d_IV - ATM_IV) / ATM_IV

    # Call skew (25-delta)
    call_25d_strike: Optional[float] = None
    call_25d_iv: Optional[float] = None
    call_skew_absolute: Optional[float] = None
    call_skew_relative: Optional[float] = None

    # Slope
    put_skew_slope: Optional[float] = None       # IV change per 1% strike distance
    call_skew_slope: Optional[float] = None

    # IV surface (strike -> IV)
    put_iv_surface: Dict[float, float] = None
    call_iv_surface: Dict[float, float] = None

    def __post_init__(self):
        if self.put_iv_surface is None:
            self.put_iv_surface = {}
        if self.call_iv_surface is None:
            self.call_iv_surface = {}


class SkewAnalyzer:
    """
    Analyze volatility skew across an option chain.

    The analyzer populates implied volatilities (if missing from API),
    identifies ATM and 25-delta strikes, and computes skew metrics.
    """

    def __init__(self, chain: OptionChain, risk_free_rate: float = 0.045):
        self.chain = chain
        self.r = risk_free_rate
        self.S = chain.underlying_price
        self.T = years_to_expiry(chain.expiration) or 0.0

    # ------------------------------------------------------------------
    # Main analysis entry point
    # ------------------------------------------------------------------

    def analyze(self) -> SkewMetrics:
        """Run full skew analysis and return SkewMetrics."""
        # Step 1: Ensure IVs are populated
        self._populate_ivs()

        # Step 2: Populate deltas
        self._populate_deltas()

        # Step 3: Find ATM
        atm_strike = self.chain.get_atm_strike()
        if atm_strike is None:
            logger.warning(f"No ATM strike found for {self.chain.ticker}")
            return SkewMetrics(
                ticker=self.chain.ticker,
                expiration=self.chain.expiration,
                underlying_price=self.S,
                atm_strike=self.S,
            )

        # Step 4: Get ATM IVs
        atm_call = self.chain.get_contract(atm_strike, "call")
        atm_put = self.chain.get_contract(atm_strike, "put")
        atm_call_iv = atm_call.implied_volatility if atm_call else None
        atm_put_iv = atm_put.implied_volatility if atm_put else None

        # Step 5: Find 25-delta strikes and IVs
        put_25d = self._find_delta_contract(target_delta=0.25, option_type="put")
        call_25d = self._find_delta_contract(target_delta=0.25, option_type="call")

        # Step 6: Build IV surfaces
        put_surface = self._build_iv_surface("put")
        call_surface = self._build_iv_surface("call")

        # Step 7: Compute skew metrics
        metrics = SkewMetrics(
            ticker=self.chain.ticker,
            expiration=self.chain.expiration,
            underlying_price=self.S,
            atm_strike=atm_strike,
            atm_call_iv=atm_call_iv,
            atm_put_iv=atm_put_iv,
            put_iv_surface=put_surface,
            call_iv_surface=call_surface,
        )

        # Put skew
        if put_25d and atm_put_iv and atm_put_iv > 0:
            metrics.put_25d_strike = put_25d.strike
            metrics.put_25d_iv = put_25d.implied_volatility
            if put_25d.implied_volatility is not None:
                metrics.put_skew_absolute = put_25d.implied_volatility - atm_put_iv
                metrics.put_skew_relative = metrics.put_skew_absolute / atm_put_iv

                # Slope: IV change per 1% of underlying price in strike distance
                strike_dist_pct = abs(put_25d.strike - atm_strike) / self.S
                if strike_dist_pct > 0:
                    metrics.put_skew_slope = metrics.put_skew_absolute / strike_dist_pct

        # Call skew
        if call_25d and atm_call_iv and atm_call_iv > 0:
            metrics.call_25d_strike = call_25d.strike
            metrics.call_25d_iv = call_25d.implied_volatility
            if call_25d.implied_volatility is not None:
                metrics.call_skew_absolute = call_25d.implied_volatility - atm_call_iv
                metrics.call_skew_relative = metrics.call_skew_absolute / atm_call_iv

                strike_dist_pct = abs(call_25d.strike - atm_strike) / self.S
                if strike_dist_pct > 0:
                    metrics.call_skew_slope = metrics.call_skew_absolute / strike_dist_pct

        return metrics

    # ------------------------------------------------------------------
    # IV population
    # ------------------------------------------------------------------

    def _populate_ivs(self):
        """
        Ensure every contract has an implied_volatility value.
        If API didn't provide one, solve for it from the market price.
        """
        if self.T <= 0 or self.S <= 0:
            return

        for contracts in [self.chain.calls, self.chain.puts]:
            for c in contracts:
                if c.implied_volatility is not None and c.implied_volatility > 0:
                    continue
                price = c.mid_price
                if price <= 0:
                    continue
                iv = implied_volatility(
                    market_price=price,
                    S=self.S,
                    K=c.strike,
                    T=self.T,
                    r=self.r,
                    option_type=c.option_type,
                )
                if iv is not None:
                    c.implied_volatility = iv

    def _populate_deltas(self):
        """Populate delta on each contract if not already set."""
        if self.T <= 0 or self.S <= 0:
            return

        for contracts in [self.chain.calls, self.chain.puts]:
            for c in contracts:
                if c.delta is not None:
                    continue
                iv = c.implied_volatility
                if iv is None or iv <= 0:
                    continue
                bs = BlackScholesCalculator(
                    self.S, c.strike, self.T, self.r, iv, c.option_type
                )
                c.delta = bs.delta()
                if c.gamma is None:
                    c.gamma = bs.gamma()
                if c.vega is None:
                    c.vega = bs.vega_pct()
                if c.theta is None:
                    c.theta = bs.theta()

    # ------------------------------------------------------------------
    # Delta-based contract finding
    # ------------------------------------------------------------------

    def _find_delta_contract(
        self, target_delta: float, option_type: str
    ) -> Optional[OptionContract]:
        """
        Find the contract closest to *target_delta* (in absolute terms).

        For puts: delta is negative, so we compare abs(delta).
        For calls: delta is positive.
        """
        source = self.chain.puts if option_type == "put" else self.chain.calls
        best = None
        best_diff = float("inf")

        for c in source:
            if c.delta is None or c.implied_volatility is None:
                continue
            if c.implied_volatility <= 0:
                continue
            diff = abs(abs(c.delta) - target_delta)
            if diff < best_diff:
                best_diff = diff
                best = c

        return best

    # ------------------------------------------------------------------
    # IV surface
    # ------------------------------------------------------------------

    def _build_iv_surface(self, option_type: str) -> Dict[float, float]:
        """Build a strike → IV mapping for the given option type."""
        source = self.chain.calls if option_type == "call" else self.chain.puts
        surface = {}
        for c in source:
            if c.implied_volatility is not None and c.implied_volatility > 0:
                surface[c.strike] = c.implied_volatility
        return surface

    # ------------------------------------------------------------------
    # Skew quality checks
    # ------------------------------------------------------------------

    @staticmethod
    def is_put_skew_attractive(metrics: SkewMetrics, min_skew: float = 0.05) -> bool:
        """
        Is put skew steep enough to make a put backspread attractive?
        A put backspread sells OTM puts (elevated IV) and buys ATM puts.
        """
        if metrics.put_skew_absolute is None:
            return False
        return metrics.put_skew_absolute >= min_skew

    @staticmethod
    def is_call_skew_attractive(metrics: SkewMetrics, min_skew: float = 0.03) -> bool:
        """
        Is call skew steep enough for a call backspread?
        Call skew is typically less pronounced in equities, so lower threshold.
        """
        if metrics.call_skew_absolute is None:
            return False
        return metrics.call_skew_absolute >= min_skew

    @staticmethod
    def skew_summary(metrics: SkewMetrics) -> str:
        """Human-readable skew summary."""
        lines = [f"Skew Analysis: {metrics.ticker} (exp {metrics.expiration})"]
        lines.append(f"  Underlying: ${metrics.underlying_price:.2f}")
        lines.append(f"  ATM Strike: ${metrics.atm_strike:.2f}")

        if metrics.atm_put_iv is not None:
            lines.append(f"  ATM Put IV:  {metrics.atm_put_iv*100:.1f}%")
        if metrics.atm_call_iv is not None:
            lines.append(f"  ATM Call IV: {metrics.atm_call_iv*100:.1f}%")

        if metrics.put_skew_absolute is not None:
            lines.append(
                f"  Put Skew (25d): {metrics.put_skew_absolute*100:+.1f}% "
                f"(relative: {metrics.put_skew_relative*100:+.1f}%)"
            )
        else:
            lines.append("  Put Skew: N/A")

        if metrics.call_skew_absolute is not None:
            lines.append(
                f"  Call Skew (25d): {metrics.call_skew_absolute*100:+.1f}% "
                f"(relative: {metrics.call_skew_relative*100:+.1f}%)"
            )
        else:
            lines.append("  Call Skew: N/A")

        return "\n".join(lines)
