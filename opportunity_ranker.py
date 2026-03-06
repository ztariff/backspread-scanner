"""
Opportunity ranking for diagonal ratio backspreads.

Scoring dimensions:
  1. Cheapness of the long leg          (40%)  — core signal
  2. Premium neutrality                 (20%)  — how well the short leg pays
  3. Tail payoff potential              (25%)  — what happens on a big move
  4. Risk profile                       (15%)  — theta/Greeks manageability
"""

import logging
from typing import List, Optional

from diagonal_constructor import DiagonalBackspread
from utils import normalize_score

logger = logging.getLogger("backspread_scanner.ranker")

# Scoring weights
CHEAPNESS_WEIGHT = 0.40
NEUTRALITY_WEIGHT = 0.20
TAIL_WEIGHT = 0.25
RISK_WEIGHT = 0.15


class OpportunityRanker:

    def __init__(
        self,
        cheapness_weight: float = CHEAPNESS_WEIGHT,
        neutrality_weight: float = NEUTRALITY_WEIGHT,
        tail_weight: float = TAIL_WEIGHT,
        risk_weight: float = RISK_WEIGHT,
    ):
        self.cheapness_weight = cheapness_weight
        self.neutrality_weight = neutrality_weight
        self.tail_weight = tail_weight
        self.risk_weight = risk_weight

    def score(self, strat: DiagonalBackspread) -> float:
        """Compute composite 0-100 score for a diagonal backspread."""
        scores = {}

        # 1. Cheapness (already 0-100 from the analyzer)
        scores["cheapness"] = min(strat.cheapness_score, 100.0)

        # 2. Premium neutrality
        # 0% deviation = perfect = 100, 20% = 0
        pn = strat.premium_neutral_pct
        if pn <= 0.01:
            scores["neutrality"] = 100.0
        elif pn >= 0.30:
            scores["neutrality"] = 0.0
        else:
            scores["neutrality"] = max(0, (0.30 - pn) / 0.30 * 100.0)

        # Bonus: if net premium is a credit (negative), even better
        if strat.net_premium < 0:
            scores["neutrality"] = min(100, scores["neutrality"] + 20)

        # 3. Tail payoff potential
        if strat.tail_payoff is not None and strat.tail_payoff > 0:
            # Normalize: $1k tail payoff = decent, $50k+ = excellent
            tail = strat.tail_payoff
            if tail <= 0:
                scores["tail"] = 0.0
            elif tail <= 1000:
                scores["tail"] = tail / 1000 * 30
            elif tail <= 10000:
                scores["tail"] = 30 + (tail - 1000) / 9000 * 30
            elif tail <= 100000:
                scores["tail"] = 60 + (tail - 10000) / 90000 * 30
            else:
                scores["tail"] = 90 + min((tail - 100000) / 100000, 1) * 10
        else:
            scores["tail"] = 25.0  # neutral

        # Also factor in the yield ratio (move_yield_ratio from cheapness)
        if strat.historical_move_yield and strat.historical_move_yield > 1:
            yield_bonus = min(strat.historical_move_yield / 50 * 20, 20)
            scores["tail"] = min(100, scores["tail"] + yield_bonus)

        # 4. Risk profile
        risk_score = 50.0  # baseline

        # Good: long vega (benefits from vol expansion)
        if strat.net_vega is not None and strat.net_vega > 0:
            risk_score += 15.0

        # Good: small daily theta bleed
        if strat.daily_theta_cost is not None:
            daily_cost = abs(strat.daily_theta_cost)
            if daily_cost < 5:
                risk_score += 10.0
            elif daily_cost < 20:
                risk_score += 5.0

        # Good: ratio >= 3 (lots of convexity per financing dollar)
        if strat.ratio >= 5:
            risk_score += 15.0
        elif strat.ratio >= 3:
            risk_score += 10.0

        # Good: manageable delta
        if strat.net_delta is not None and abs(strat.net_delta) < 100:
            risk_score += 10.0

        # Bad: large gap between long & short strikes means long legs
        # won't respond when short legs are tested
        if strat.gap_risk is not None and strat.gap_risk > 0:
            gap_penalty = min(strat.gap_risk / 500, 1.0) * 30.0
            risk_score = max(0, risk_score - gap_penalty)

        scores["risk"] = min(risk_score, 100.0)

        # Composite
        composite = (
            self.cheapness_weight * scores["cheapness"]
            + self.neutrality_weight * scores["neutrality"]
            + self.tail_weight * scores["tail"]
            + self.risk_weight * scores["risk"]
        )

        strat.score = round(composite, 1)
        return composite

    def rank(
        self,
        strategies: List[DiagonalBackspread],
        top_n: int = 25,
    ) -> List[DiagonalBackspread]:
        """Score and rank all strategies. Returns top N by score."""
        for s in strategies:
            self.score(s)

        ranked = sorted(strategies, key=lambda s: s.score, reverse=True)

        if top_n:
            ranked = ranked[:top_n]

        logger.info(f"Ranked {len(strategies)} strategies, returning top {len(ranked)}")
        return ranked

    def filter(
        self,
        strategies: List[DiagonalBackspread],
        min_score: float = 0.0,
        direction: Optional[str] = None,
        max_net_premium: Optional[float] = None,
        min_ratio: float = 2.0,
    ) -> List[DiagonalBackspread]:
        """Filter strategies by various criteria."""
        filtered = strategies

        if direction:
            filtered = [s for s in filtered if s.direction == direction]

        if min_score > 0:
            filtered = [s for s in filtered if s.score >= min_score]

        if max_net_premium is not None:
            filtered = [s for s in filtered if s.net_premium <= max_net_premium]

        if min_ratio > 0:
            filtered = [s for s in filtered if s.ratio >= min_ratio]

        return filtered
