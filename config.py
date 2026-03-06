"""
Configuration management for the Diagonal Ratio Backspread Scanner.
Loads settings from environment variables and provides sensible defaults.
"""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """Scanner configuration with environment variable overrides."""

    # ── Polygon.io ──────────────────────────────────────────────────
    polygon_api_key: str = ""
    rate_limit_pause: float = 0.25  # seconds between API calls

    # ── Long Leg (far OTM — the "lottery tickets") ──────────────
    long_min_dte: int = 0            # 0 = same-day (0DTE) allowed
    long_max_dte: int = 120          # maximum DTE for long leg
    long_min_otm_pct: float = 0.03   # min distance OTM as % of underlying (3%)
    long_max_otm_pct: float = 0.18   # max distance OTM (18%) — keep longs close enough to respond
    max_strike_gap_pct: float = 0.02 # max gap between long & short strikes — longs must be near-adjacent
    long_max_price: float = 5.00     # max per-contract price for "cheap" (dollars)
    long_min_price: float = 0.05     # min per-contract price — must have SOME value
    long_max_delta: float = 0.20     # max abs(delta) — must be far OTM
    long_min_delta: float = 0.02     # min abs(delta) — must have some sensitivity

    # ── Short Leg (ATM-ish — the "financing leg") ─────────────
    short_min_dte: int = 0           # 0 = same-day (0DTE) allowed
    short_max_dte: int = 14          # maximum DTE for short leg
    short_min_delta: float = 0.25    # min abs(delta) — needs enough premium
    short_max_delta: float = 0.60    # max abs(delta) — ATM-ish

    # ── Ticker Universe ───────────────────────────────────────────
    default_tickers: tuple = (
        "SPY", "QQQ", "TSLA", "AAPL", "AMD", "MU", "NVDA",
        "GLD", "SLV", "TLT",
        "META", "AMZN", "GOOGL", "MSFT", "NFLX",
        "COIN", "MARA", "SMCI", "ARM", "PLTR",
    )

    # ── Cheapness Thresholds ────────────────────────────────────────
    # Equidistant comparison: how much cheaper must the target wing be
    # vs. the opposite-side equidistant option (as a ratio)
    min_equidistant_ratio: float = 2.0   # OTM put must be ≥2× the OTM call (or vice versa)

    # Historical move comparison: option price as multiple of theoretical
    # fair value based on realized vol
    max_iv_to_rv_ratio: float = 1.0      # IV should be ≤ realized vol (underpriced)

    # Absolute cheapness
    max_cheap_price: float = 2.00        # maximum price to consider "cheap" ($)

    # ── Premium Neutrality ──────────────────────────────────────────
    premium_neutral_tolerance: float = 0.20  # allow ±20% deviation from neutral

    # ── Liquidity Filters ───────────────────────────────────────────
    min_option_volume: int = 5
    min_open_interest: int = 20
    max_bid_ask_pct: float = 0.50        # wider tolerance for cheap OTM options

    # ── Historical Data ─────────────────────────────────────────────
    realized_vol_lookback: int = 252     # trading days for realized vol
    max_move_lookback: int = 252         # days to look back for largest moves

    # ── Pricing ─────────────────────────────────────────────────────
    risk_free_rate: float = 0.045

    # ── Output ──────────────────────────────────────────────────────
    output_dir: str = "."
    top_n: int = 25

    @classmethod
    def from_env(cls):
        """Build config with environment variable overrides."""
        cfg = cls()
        cfg.polygon_api_key = os.environ.get("POLYGON_API_KEY", "")

        env_map = [
            ("POLYGON_RATE_LIMIT", "rate_limit_pause", float),
            ("DIAG_LONG_MIN_DTE", "long_min_dte", int),
            ("DIAG_LONG_MAX_DTE", "long_max_dte", int),
            ("DIAG_LONG_MIN_OTM_PCT", "long_min_otm_pct", float),
            ("DIAG_LONG_MAX_OTM_PCT", "long_max_otm_pct", float),
            ("DIAG_LONG_MAX_PRICE", "long_max_price", float),
            ("DIAG_LONG_MAX_DELTA", "long_max_delta", float),
            ("DIAG_SHORT_MIN_DTE", "short_min_dte", int),
            ("DIAG_SHORT_MAX_DTE", "short_max_dte", int),
            ("DIAG_SHORT_MIN_DELTA", "short_min_delta", float),
            ("DIAG_SHORT_MAX_DELTA", "short_max_delta", float),
            ("DIAG_MIN_EQUIDIST_RATIO", "min_equidistant_ratio", float),
            ("DIAG_MAX_IV_RV_RATIO", "max_iv_to_rv_ratio", float),
            ("DIAG_MAX_CHEAP_PRICE", "max_cheap_price", float),
            ("DIAG_PREMIUM_NEUTRAL_TOL", "premium_neutral_tolerance", float),
            ("DIAG_MIN_VOLUME", "min_option_volume", int),
            ("DIAG_MIN_OI", "min_open_interest", int),
            ("DIAG_RV_LOOKBACK", "realized_vol_lookback", int),
            ("DIAG_RISK_FREE_RATE", "risk_free_rate", float),
            ("DIAG_TOP_N", "top_n", int),
        ]

        for env_key, attr, cast in env_map:
            val = os.environ.get(env_key)
            if val is not None:
                try:
                    setattr(cfg, attr, cast(val))
                except (ValueError, TypeError):
                    pass

        return cfg

    def validate(self):
        """Return a list of validation error strings (empty if OK)."""
        errors = []
        if not self.polygon_api_key:
            errors.append(
                "POLYGON_API_KEY is not set. "
                "Export it as an environment variable or add it to .env"
            )
        if self.long_min_dte < 0:
            errors.append("long_min_dte must be >= 0")
        return errors
