"""
Diagonal ratio backspread constructor.

Builds the complete trade:
  LONG LEG:  Buy N contracts of far-OTM options on a longer expiry (cheap convexity)
  SHORT LEG: Sell M contracts of ATM/near-ATM options on a shorter expiry (financing)

Where N > M, and the trade is structured near premium-neutral so the
short leg pays for the long leg.

Same direction only: long calls + short calls, or long puts + short puts.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

from option_chain import OptionChain, OptionContract
from cheapness_analyzer import CheapnessReport
from greeks_calculator import BlackScholesCalculator
from utils import years_to_expiry

logger = logging.getLogger("backspread_scanner.diagonal")


@dataclass
class DiagonalLeg:
    """One leg of the diagonal ratio backspread."""
    contract: OptionContract
    quantity: int           # positive = long, negative = short
    entry_price: float      # per-contract mid-price

    @property
    def strike(self):
        return self.contract.strike

    @property
    def option_type(self):
        return self.contract.option_type

    @property
    def expiration(self):
        return self.contract.expiration

    @property
    def total_cost(self):
        """Signed cost in dollars. Negative = credit received."""
        return self.quantity * self.entry_price * 100

    @property
    def notional(self):
        """Absolute dollar commitment."""
        return abs(self.total_cost)


@dataclass
class DiagonalBackspread:
    """
    Complete diagonal ratio backspread structure.

    long_leg:  far-OTM, longer expiry, many contracts (the convexity)
    short_leg: ATM-ish, shorter expiry, fewer contracts (the financing)
    """
    ticker: str
    direction: str              # "call" or "put"
    underlying_price: float

    long_leg: DiagonalLeg       # far OTM, longer expiry, large qty
    short_leg: DiagonalLeg      # near ATM, shorter expiry, small qty

    # Cheapness context from the analyzer
    cheapness_score: float = 0.0
    equidistant_ratio: Optional[float] = None
    iv_rv_ratio: Optional[float] = None
    historical_move_yield: Optional[float] = None

    # Financing metrics
    net_premium: float = 0.0        # net cost of the whole trade ($)
    premium_neutral_pct: float = 0.0  # how close to zero-cost (0 = perfect)
    long_qty: int = 0
    short_qty: int = 0
    ratio: float = 0.0              # long_qty / short_qty

    # Greeks (at entry)
    net_delta: Optional[float] = None
    net_gamma: Optional[float] = None
    net_vega: Optional[float] = None
    net_theta: Optional[float] = None

    # Strike gap risk
    gap_risk: Optional[float] = None            # dollar risk in the dead zone between strikes

    # Scenario analysis
    tail_payoff: Optional[float] = None       # P&L if max historical move repeats
    short_leg_max_loss: Optional[float] = None  # worst case on short leg alone
    daily_theta_cost: Optional[float] = None    # daily carrying cost/income

    # Overall score
    score: float = 0.0

    @property
    def long_expiry(self):
        return self.long_leg.expiration

    @property
    def short_expiry(self):
        return self.short_leg.expiration

    def compute_greeks(self, risk_free_rate: float = 0.045):
        """Compute aggregate Greeks."""
        total_d = total_g = total_v = total_t = 0.0

        for leg in [self.long_leg, self.short_leg]:
            iv = leg.contract.implied_volatility
            if iv is None or iv <= 0:
                continue
            T = years_to_expiry(leg.expiration)
            if T is None or T <= 0:
                continue
            bs = BlackScholesCalculator(
                self.underlying_price, leg.strike, T,
                risk_free_rate, iv, leg.option_type,
            )
            total_d += bs.delta() * leg.quantity * 100
            total_g += bs.gamma() * leg.quantity * 100
            total_v += bs.vega_pct() * leg.quantity * 100
            total_t += bs.theta() * leg.quantity * 100

        self.net_delta = total_d
        self.net_gamma = total_g
        self.net_vega = total_v
        self.net_theta = total_t
        self.daily_theta_cost = total_t

    def summary_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "direction": self.direction,
            "long_strike": self.long_leg.strike,
            "long_exp": self.long_leg.expiration,
            "long_price": round(self.long_leg.entry_price, 2),
            "long_qty": self.long_qty,
            "short_strike": self.short_leg.strike,
            "short_exp": self.short_leg.expiration,
            "short_price": round(self.short_leg.entry_price, 2),
            "short_qty": self.short_qty,
            "ratio": f"{self.long_qty}:{self.short_qty}",
            "net_premium": round(self.net_premium, 2),
            "premium_neutral_pct": round(self.premium_neutral_pct * 100, 1),
            "cheapness": round(self.cheapness_score, 1),
            "equidist_ratio": round(self.equidistant_ratio or 0, 1),
            "iv_rv": round(self.iv_rv_ratio or 0, 2),
            "hist_move_yield": round(self.historical_move_yield or 0, 0),
            "gap_risk": round(self.gap_risk or 0, 0),
            "tail_payoff": round(self.tail_payoff or 0, 0),
            "net_delta": round(self.net_delta or 0, 1),
            "net_vega": round(self.net_vega or 0, 1),
            "net_theta": round(self.net_theta or 0, 2),
            "score": round(self.score, 1),
        }


# ======================================================================
# Builder
# ======================================================================

def find_financing_legs(
    short_chain: OptionChain,
    option_type: str,
    min_delta: float = 0.25,
    max_delta: float = 0.60,
) -> List[OptionContract]:
    """
    Find ATM-ish options on the short-dated expiry that can be sold
    to finance the long leg.
    """
    source = short_chain.calls if option_type == "call" else short_chain.puts
    candidates = []

    for c in source:
        if c.mid_price <= 0.05:
            continue
        # Delta check (if available)
        if c.delta is not None:
            if abs(c.delta) < min_delta or abs(c.delta) > max_delta:
                continue
        else:
            # Fallback: use moneyness as proxy
            moneyness = c.strike / short_chain.underlying_price
            if option_type == "call":
                if moneyness < 0.95 or moneyness > 1.10:
                    continue
            else:
                if moneyness < 0.90 or moneyness > 1.05:
                    continue
        candidates.append(c)

    # Sort by premium (highest first — best financing)
    candidates.sort(key=lambda c: c.mid_price, reverse=True)
    return candidates


def calculate_premium_neutral_ratio(
    long_price: float,
    short_price: float,
    tolerance: float = 0.20,
) -> Tuple[int, int]:
    """
    Calculate the ratio of long:short contracts to achieve near premium neutrality.

    Returns (long_qty, short_qty) where:
      long_qty × long_price ≈ short_qty × short_price

    We want to buy many cheap options and sell fewer expensive ones.
    """
    if long_price <= 0 or short_price <= 0:
        return (0, 0)

    # How many long contracts can 1 short contract finance?
    contracts_per_short = short_price / long_price

    # Try small short quantities and scale up
    best = None
    best_neutral = float("inf")

    for short_qty in range(1, 20):
        # Exact long qty for perfect neutrality
        exact_long = short_qty * contracts_per_short
        long_qty = round(exact_long)

        if long_qty < 2:
            continue  # need at least 2x ratio
        if long_qty <= short_qty:
            continue  # must be more longs than shorts

        # How close to neutral?
        long_cost = long_qty * long_price
        short_credit = short_qty * short_price
        net = long_cost - short_credit
        neutrality = abs(net) / max(long_cost, 0.01)

        if neutrality <= tolerance:
            if best is None or neutrality < best_neutral:
                best = (long_qty, short_qty)
                best_neutral = neutrality

    # If we found nothing within tolerance, return the best non-zero ratio
    if best is None:
        long_qty = max(2, round(contracts_per_short))
        return (long_qty, 1)

    return best


def build_diagonal_backspreads(
    cheap_reports: List[CheapnessReport],
    short_chain: OptionChain,
    config,
) -> List[DiagonalBackspread]:
    """
    Build diagonal ratio backspreads by pairing:
      - Cheap far-OTM options (from cheapness analysis) as the long leg
      - ATM-ish options from a shorter expiry as the short leg

    Parameters
    ----------
    cheap_reports : list of CheapnessReport (the cheap options found)
    short_chain   : OptionChain for the short-dated expiry
    config        : Config object

    Returns list of DiagonalBackspread structures.
    """
    strategies = []

    for report in cheap_reports:
        long_contract = report.contract
        option_type = long_contract.option_type

        # Find financing candidates on the short expiry
        financing = find_financing_legs(
            short_chain,
            option_type=option_type,
            min_delta=config.short_min_delta,
            max_delta=config.short_max_delta,
        )

        if not financing:
            continue

        # Try pairing with each financing candidate
        for short_contract in financing[:5]:  # top 5 by premium
            long_price = long_contract.mid_price
            short_price = short_contract.mid_price

            if long_price <= 0 or short_price <= 0:
                continue

            # Strike gap constraint: long leg must be close enough to respond
            # when short leg is tested
            strike_gap = abs(long_contract.strike - short_contract.strike)
            max_gap_pct = getattr(config, 'max_strike_gap_pct', 0.10)
            if strike_gap / report.underlying_price > max_gap_pct:
                continue

            # Calculate premium-neutral ratio
            long_qty, short_qty = calculate_premium_neutral_ratio(
                long_price, short_price,
                tolerance=config.premium_neutral_tolerance,
            )

            if long_qty < 2 or short_qty < 1:
                continue

            # Aggregate delta check: longs × delta must exceed shorts × delta
            # so position accelerates in your favor past the short strike
            if long_contract.delta is not None and short_contract.delta is not None:
                agg_long_d = abs(long_contract.delta) * long_qty
                agg_short_d = abs(short_contract.delta) * short_qty
                if agg_long_d < agg_short_d * 0.5:
                    continue

            # Build the structure
            long_leg = DiagonalLeg(
                contract=long_contract,
                quantity=long_qty,
                entry_price=long_price,
            )
            short_leg = DiagonalLeg(
                contract=short_contract,
                quantity=-short_qty,
                entry_price=short_price,
            )

            net_premium = long_leg.total_cost + short_leg.total_cost
            long_total = long_leg.notional
            premium_neutral_pct = abs(net_premium) / max(long_total, 1)

            strat = DiagonalBackspread(
                ticker=long_contract.ticker,
                direction=option_type,
                underlying_price=report.underlying_price,
                long_leg=long_leg,
                short_leg=short_leg,
                cheapness_score=report.composite_cheapness,
                equidistant_ratio=report.equidistant_ratio,
                iv_rv_ratio=report.iv_rv_ratio,
                historical_move_yield=report.move_yield_ratio,
                net_premium=net_premium,
                premium_neutral_pct=premium_neutral_pct,
                long_qty=long_qty,
                short_qty=short_qty,
                ratio=long_qty / short_qty,
            )

            # Gap risk: max loss in the dead zone between long and short strikes
            strat.gap_risk = strike_gap * short_qty * 100

            # Compute Greeks
            strat.compute_greeks(config.risk_free_rate)

            # Tail payoff estimate
            if report.move_would_yield is not None:
                strat.tail_payoff = (
                    report.move_would_yield * long_qty * 100
                    - abs(net_premium)
                )

            # Short leg max loss: if underlying moves through short strike
            short_itm_move = abs(short_contract.strike - report.underlying_price)
            strat.short_leg_max_loss = (
                short_itm_move * short_qty * 100
                + net_premium
            )

            strategies.append(strat)

    return strategies
