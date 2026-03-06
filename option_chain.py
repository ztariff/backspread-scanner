"""
Data models for option contracts and option chains.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import date


@dataclass
class OptionContract:
    """Single option contract with market data."""

    ticker: str
    strike: float
    expiration: str          # ISO date string
    option_type: str         # "call" or "put"
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    volume: int = 0
    open_interest: int = 0
    implied_volatility: Optional[float] = None
    contract_symbol: str = ""

    # Computed Greeks (populated later)
    delta: Optional[float] = None
    gamma: Optional[float] = None
    vega: Optional[float] = None
    theta: Optional[float] = None

    @property
    def mid_price(self):
        """Mid-point of bid/ask."""
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.last or 0.0

    @property
    def spread(self):
        """Absolute bid-ask spread."""
        if self.bid > 0 and self.ask > 0:
            return self.ask - self.bid
        return 0.0

    @property
    def spread_pct(self):
        """Bid-ask spread as a percentage of mid-price."""
        mid = self.mid_price
        if mid > 0:
            return self.spread / mid
        return float("inf")

    def liquidity_score(self):
        """Simple liquidity heuristic: volume × OI / (1 + spread_pct)."""
        return (self.volume * self.open_interest) / (1.0 + self.spread_pct)

    def is_liquid(self, min_volume=10, min_oi=50, max_spread_pct=0.20):
        """Check if contract meets minimum liquidity requirements."""
        return (
            self.volume >= min_volume
            and self.open_interest >= min_oi
            and (self.spread_pct <= max_spread_pct or self.spread_pct == float("inf"))
            and self.mid_price > 0.05
        )


@dataclass
class OptionChain:
    """
    Full option chain for a single ticker and expiration.
    """

    ticker: str
    expiration: str
    underlying_price: float = 0.0
    calls: List[OptionContract] = field(default_factory=list)
    puts: List[OptionContract] = field(default_factory=list)

    def sort_by_strike(self):
        """Sort calls and puts by strike price."""
        self.calls.sort(key=lambda c: c.strike)
        self.puts.sort(key=lambda p: p.strike)

    def get_atm_strike(self):
        """Return the strike closest to the underlying price."""
        all_strikes = set(c.strike for c in self.calls) | set(p.strike for p in self.puts)
        if not all_strikes:
            return None
        return min(all_strikes, key=lambda s: abs(s - self.underlying_price))

    def get_calls_by_strike_range(self, low, high):
        """Return calls with strikes in [low, high]."""
        return [c for c in self.calls if low <= c.strike <= high]

    def get_puts_by_strike_range(self, low, high):
        """Return puts with strikes in [low, high]."""
        return [p for p in self.puts if low <= p.strike <= high]

    def get_contract(self, strike, option_type):
        """Find a specific contract by strike and type."""
        source = self.calls if option_type == "call" else self.puts
        for c in source:
            if abs(c.strike - strike) < 0.005:
                return c
        return None

    def get_liquid_calls(self, min_volume=10, min_oi=50, max_spread_pct=0.20):
        """Return calls that meet liquidity thresholds."""
        return [c for c in self.calls if c.is_liquid(min_volume, min_oi, max_spread_pct)]

    def get_liquid_puts(self, min_volume=10, min_oi=50, max_spread_pct=0.20):
        """Return puts that meet liquidity thresholds."""
        return [p for p in self.puts if p.is_liquid(min_volume, min_oi, max_spread_pct)]

    def get_contracts_by_delta(self, delta_low, delta_high, option_type):
        """
        Return contracts whose delta falls within [delta_low, delta_high].
        Deltas must already be populated on the contracts.
        """
        source = self.calls if option_type == "call" else self.puts
        return [
            c for c in source
            if c.delta is not None and delta_low <= abs(c.delta) <= delta_high
        ]

    @property
    def call_strikes(self):
        return sorted(set(c.strike for c in self.calls))

    @property
    def put_strikes(self):
        return sorted(set(p.strike for p in self.puts))

    def __repr__(self):
        return (
            f"OptionChain({self.ticker} exp={self.expiration} "
            f"S={self.underlying_price:.2f} "
            f"calls={len(self.calls)} puts={len(self.puts)})"
        )
