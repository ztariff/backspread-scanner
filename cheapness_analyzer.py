"""
Cheapness analysis for far-OTM options.

Identifies options that are "cheap" by multiple measures:

1. EQUIDISTANT COMPARISON — a $50 OTM call costs far less than the $50 OTM put
   (or vice versa). This asymmetry means one wing is underpriced relative to
   the other.

2. IV vs REALIZED VOL — the option's implied volatility is low relative to
   the underlying's realized volatility. The market is underpricing the
   probability of a move that has historically occurred.

3. PRICE vs HISTORICAL MOVES — the option costs pennies, but the underlying
   has moved far enough to put that option deep ITM within the lookback period.
   The move *has happened before* and the option doesn't price it.

4. ABSOLUTE CHEAPNESS — the option is just plain cheap in dollar terms,
   which is a prerequisite for accumulating large quantities.

5. WING LOADING — the entire OTM wing has collapsed in IV while the opposite
   wing remains bid. Systemic mispricing of one tail.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

from option_chain import OptionChain, OptionContract
from greeks_calculator import BlackScholesCalculator, implied_volatility, option_price
from utils import years_to_expiry

logger = logging.getLogger("backspread_scanner.cheapness")


@dataclass
class CheapnessReport:
    """Analysis of how cheap a specific OTM option is."""

    contract: OptionContract
    underlying_price: float

    # Distance from ATM
    otm_distance: float = 0.0          # dollars
    otm_distance_pct: float = 0.0      # as % of underlying

    # Measure 1: Equidistant comparison
    mirror_price: Optional[float] = None         # price of equidistant opposite-side option
    equidistant_ratio: Optional[float] = None     # mirror_price / this_price (higher = cheaper)
    equidistant_score: float = 0.0                # 0-100

    # Measure 2: IV vs realized vol
    option_iv: Optional[float] = None
    realized_vol: Optional[float] = None
    iv_rv_ratio: Optional[float] = None           # IV / RV (< 1 = underpriced)
    iv_rv_score: float = 0.0

    # Measure 3: Price vs historical moves
    option_price_dollars: float = 0.0
    max_historical_move_pct: Optional[float] = None   # largest move in the option's direction
    move_would_yield: Optional[float] = None           # intrinsic value if max move repeated
    move_yield_ratio: Optional[float] = None           # move_would_yield / option_price
    historical_move_score: float = 0.0

    # Measure 4: Absolute cheapness
    absolute_price_score: float = 0.0  # cheaper = higher score

    # Measure 5: Wing IV collapse
    wing_avg_iv: Optional[float] = None
    opposite_wing_avg_iv: Optional[float] = None
    wing_iv_ratio: Optional[float] = None      # opposite / same (higher = this wing is cheap)
    wing_loading_score: float = 0.0

    # Composite
    composite_cheapness: float = 0.0

    def summary(self) -> str:
        opt = self.contract
        direction = "↑" if opt.option_type == "call" else "↓"
        return (
            f"{opt.ticker} {opt.option_type.upper()} ${opt.strike:.0f} "
            f"({self.otm_distance_pct*100:+.1f}% OTM {direction}) "
            f"@ ${self.option_price_dollars:.2f} | "
            f"Cheapness: {self.composite_cheapness:.1f}/100"
        )


class CheapnessAnalyzer:
    """
    Multi-dimensional cheapness analysis for OTM options.

    The analyzer computes cheapness across five dimensions and produces
    a composite score. Higher score = cheaper = more attractive for
    the long leg of a diagonal ratio backspread.
    """

    # Scoring weights
    EQUIDISTANT_WEIGHT = 0.30      # biggest signal: relative mispricing
    IV_RV_WEIGHT = 0.20            # IV below realized vol
    HISTORICAL_MOVE_WEIGHT = 0.25  # price doesn't reflect past moves
    ABSOLUTE_PRICE_WEIGHT = 0.10   # plain cheap in dollar terms
    WING_LOADING_WEIGHT = 0.15     # one wing systematically cheap

    def __init__(
        self,
        chain: OptionChain,
        realized_vol: Optional[float] = None,
        max_moves: Optional[Dict] = None,
        risk_free_rate: float = 0.045,
    ):
        self.chain = chain
        self.S = chain.underlying_price
        self.rv = realized_vol
        self.max_moves = max_moves or {}
        self.r = risk_free_rate
        self.T = years_to_expiry(chain.expiration) or 0.001

    def analyze_contract(self, contract: OptionContract) -> CheapnessReport:
        """Full cheapness analysis of a single OTM option."""
        report = CheapnessReport(
            contract=contract,
            underlying_price=self.S,
            option_price_dollars=contract.mid_price,
        )

        # Basic distance
        if contract.option_type == "call":
            report.otm_distance = contract.strike - self.S
        else:
            report.otm_distance = self.S - contract.strike
        report.otm_distance_pct = report.otm_distance / self.S if self.S > 0 else 0

        # Ensure IV is populated
        iv = contract.implied_volatility
        if iv is None or iv <= 0:
            iv = implied_volatility(
                contract.mid_price, self.S, contract.strike,
                self.T, self.r, contract.option_type,
            )
            if iv:
                contract.implied_volatility = iv
        report.option_iv = iv

        # ── Measure 1: Equidistant comparison ──
        self._score_equidistant(report)

        # ── Measure 2: IV vs realized vol ──
        self._score_iv_vs_rv(report)

        # ── Measure 3: Price vs historical moves ──
        self._score_historical_moves(report)

        # ── Measure 4: Absolute cheapness ──
        self._score_absolute_price(report)

        # ── Measure 5: Wing loading ──
        self._score_wing_loading(report)

        # ── Composite ──
        report.composite_cheapness = (
            self.EQUIDISTANT_WEIGHT * report.equidistant_score
            + self.IV_RV_WEIGHT * report.iv_rv_score
            + self.HISTORICAL_MOVE_WEIGHT * report.historical_move_score
            + self.ABSOLUTE_PRICE_WEIGHT * report.absolute_price_score
            + self.WING_LOADING_WEIGHT * report.wing_loading_score
        )

        return report

    def find_cheap_options(
        self,
        option_type: str = "both",
        max_delta: float = 0.20,
        min_delta: float = 0.02,
        min_otm_pct: float = 0.05,
        max_otm_pct: float = 0.40,
        max_price: float = 5.00,
        min_price: float = 0.05,
        min_score: float = 30.0,
    ) -> List[CheapnessReport]:
        """
        Scan the chain for cheap far-OTM options.

        Parameters
        ----------
        option_type : "call", "put", or "both"
        max_delta   : max abs(delta) — must be far OTM
        min_delta   : min abs(delta) — must have some sensitivity
        min_otm_pct : minimum distance OTM as % of underlying
        max_otm_pct : maximum distance OTM
        max_price   : maximum option price (must be "cheap")
        min_price   : minimum option price — must have SOME value, not worthless
        min_score   : minimum composite cheapness score to include
        """
        candidates = []

        contracts = []
        if option_type in ("call", "both"):
            contracts.extend(self.chain.calls)
        if option_type in ("put", "both"):
            contracts.extend(self.chain.puts)

        for c in contracts:
            # Filter: must be OTM
            if c.option_type == "call" and c.strike <= self.S:
                continue
            if c.option_type == "put" and c.strike >= self.S:
                continue

            # Filter: distance OTM
            dist_pct = abs(c.strike - self.S) / self.S if self.S > 0 else 0
            if dist_pct < min_otm_pct or dist_pct > max_otm_pct:
                continue

            # Filter: must be cheap but not worthless
            if c.mid_price > max_price or c.mid_price < min_price:
                continue

            # Filter: delta (if available) — not too deep OTM and not too worthless
            if c.delta is not None:
                if abs(c.delta) > max_delta or abs(c.delta) < min_delta:
                    continue

            report = self.analyze_contract(c)
            if report.composite_cheapness >= min_score:
                candidates.append(report)

        # Sort by cheapness (highest = cheapest = best)
        candidates.sort(key=lambda r: r.composite_cheapness, reverse=True)
        return candidates

    # ==================================================================
    # Scoring methods
    # ==================================================================

    def _score_equidistant(self, report: CheapnessReport):
        """
        Compare this option's price to the equidistant option on
        the opposite side of the chain.

        Example: if this is a $50 OTM call, find the $50 OTM put.
        If the put is 5× more expensive, the call is very cheap.
        """
        contract = report.contract
        distance = abs(contract.strike - self.S)

        if contract.option_type == "call":
            mirror_strike = self.S - distance
            mirror_type = "put"
        else:
            mirror_strike = self.S + distance
            mirror_type = "call"

        # Find closest strike to mirror
        mirror = self._find_nearest_contract(mirror_strike, mirror_type)

        if mirror and mirror.mid_price > 0 and report.option_price_dollars > 0:
            report.mirror_price = mirror.mid_price
            report.equidistant_ratio = mirror.mid_price / report.option_price_dollars

            # Score: ratio of 1 = no edge, ratio of 5+ = very cheap
            # Map [1, 10] → [0, 100]
            ratio = min(report.equidistant_ratio, 10.0)
            report.equidistant_score = max(0, (ratio - 1.0) / 9.0 * 100.0)
        else:
            report.equidistant_score = 0.0

    def _score_iv_vs_rv(self, report: CheapnessReport):
        """
        If IV < realized vol, the option is underpricing actual volatility.
        """
        report.realized_vol = self.rv

        if report.option_iv and self.rv and self.rv > 0:
            report.iv_rv_ratio = report.option_iv / self.rv

            # Score: ratio < 0.5 = very underpriced (100), ratio > 1.5 = overpriced (0)
            if report.iv_rv_ratio <= 0.5:
                report.iv_rv_score = 100.0
            elif report.iv_rv_ratio >= 1.5:
                report.iv_rv_score = 0.0
            else:
                # Linear: 0.5→100, 1.0→50, 1.5→0
                report.iv_rv_score = max(0, (1.5 - report.iv_rv_ratio) / 1.0 * 100.0)
        else:
            report.iv_rv_score = 50.0  # neutral if data unavailable

    def _score_historical_moves(self, report: CheapnessReport):
        """
        Has the underlying ever moved enough to put this option deep ITM?
        If yes, and the option costs pennies, it's mispriced.
        """
        if not self.max_moves or report.option_price_dollars <= 0:
            report.historical_move_score = 50.0  # neutral
            return

        contract = report.contract

        # Find the relevant max move
        if contract.option_type == "call":
            # For calls, we care about the biggest up moves
            max_move = self.max_moves.get("max_up_pct", 0)
            max_multi = max(
                self.max_moves.get("max_5d_up", 0),
                self.max_moves.get("max_10d_up", 0),
                self.max_moves.get("max_20d_up", 0),
            )
        else:
            max_move = abs(self.max_moves.get("max_down_pct", 0))
            max_multi = max(
                abs(self.max_moves.get("max_5d_down", 0)),
                abs(self.max_moves.get("max_10d_down", 0)),
                abs(self.max_moves.get("max_20d_down", 0)),
            )

        # Use the larger of single-day or multi-day
        biggest_move = max(max_move, max_multi)
        report.max_historical_move_pct = biggest_move

        if biggest_move > 0 and self.S > 0:
            # If the biggest historical move repeated, what would this option be worth?
            if contract.option_type == "call":
                projected_price = self.S * (1 + biggest_move)
                intrinsic = max(projected_price - contract.strike, 0)
            else:
                projected_price = self.S * (1 - biggest_move)
                intrinsic = max(contract.strike - projected_price, 0)

            report.move_would_yield = intrinsic

            if intrinsic > 0:
                report.move_yield_ratio = intrinsic / report.option_price_dollars

                # Score: yield ratio of 1 = breakeven, 10+ = 10x return, 100+ = extreme
                ratio = min(report.move_yield_ratio, 200.0)
                if ratio <= 1:
                    report.historical_move_score = 0.0
                elif ratio <= 10:
                    report.historical_move_score = (ratio - 1) / 9 * 60  # 0-60
                elif ratio <= 100:
                    report.historical_move_score = 60 + (ratio - 10) / 90 * 30  # 60-90
                else:
                    report.historical_move_score = 90 + min((ratio - 100) / 100, 1) * 10  # 90-100
            else:
                # Even the biggest historical move wouldn't reach this strike
                report.historical_move_score = 0.0
        else:
            report.historical_move_score = 50.0

    def _score_absolute_price(self, report: CheapnessReport):
        """
        Cheap in dollar terms. Penny options score highest.
        """
        price = report.option_price_dollars
        if price <= 0:
            report.absolute_price_score = 0.0
        elif price <= 0.05:
            report.absolute_price_score = 100.0
        elif price <= 0.10:
            report.absolute_price_score = 90.0
        elif price <= 0.25:
            report.absolute_price_score = 75.0
        elif price <= 0.50:
            report.absolute_price_score = 60.0
        elif price <= 1.00:
            report.absolute_price_score = 45.0
        elif price <= 2.00:
            report.absolute_price_score = 30.0
        elif price <= 5.00:
            report.absolute_price_score = 15.0
        else:
            report.absolute_price_score = 0.0

    def _score_wing_loading(self, report: CheapnessReport):
        """
        Is the entire wing (call side or put side) cheap relative to
        the opposite wing? Systemic mispricing.
        """
        contract = report.contract

        # Average IV of the same-side OTM wing
        same_wing = self._avg_otm_iv(contract.option_type)
        opp_type = "put" if contract.option_type == "call" else "call"
        opp_wing = self._avg_otm_iv(opp_type)

        report.wing_avg_iv = same_wing
        report.opposite_wing_avg_iv = opp_wing

        if same_wing and opp_wing and same_wing > 0:
            report.wing_iv_ratio = opp_wing / same_wing

            # Score: ratio > 1 means opposite wing is more expensive
            # ratio 1.5 = this wing is 33% cheaper → high score
            ratio = report.wing_iv_ratio
            if ratio <= 1.0:
                report.wing_loading_score = 0.0
            elif ratio <= 2.0:
                report.wing_loading_score = (ratio - 1.0) * 100.0
            else:
                report.wing_loading_score = 100.0
        else:
            report.wing_loading_score = 50.0  # neutral

    # ==================================================================
    # Helpers
    # ==================================================================

    def _find_nearest_contract(
        self, target_strike: float, option_type: str
    ) -> Optional[OptionContract]:
        """Find the contract closest to *target_strike*."""
        source = self.chain.calls if option_type == "call" else self.chain.puts
        if not source:
            return None
        return min(source, key=lambda c: abs(c.strike - target_strike))

    def _avg_otm_iv(self, option_type: str) -> Optional[float]:
        """Average IV of OTM options on one side."""
        source = self.chain.calls if option_type == "call" else self.chain.puts
        ivs = []
        for c in source:
            if c.implied_volatility and c.implied_volatility > 0:
                if option_type == "call" and c.strike > self.S:
                    ivs.append(c.implied_volatility)
                elif option_type == "put" and c.strike < self.S:
                    ivs.append(c.implied_volatility)
        return sum(ivs) / len(ivs) if ivs else None
