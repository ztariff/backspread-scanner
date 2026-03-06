"""
Utility functions for the Backspread Scanner toolkit.
Includes normal distribution approximations, logging, validation helpers.
"""

import math
import logging
from datetime import datetime, date


def setup_logging(verbose=False):
    """Configure logging for the scanner."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("backspread_scanner")


# ---------------------------------------------------------------------------
# Normal distribution functions (no scipy dependency)
# ---------------------------------------------------------------------------

def norm_cdf(x):
    """
    Cumulative distribution function for the standard normal distribution.
    Uses Abramowitz & Stegun approximation (error < 1.5e-7).
    """
    a1 = 0.254829592
    a2 = -0.284496736
    a3 = 1.421413741
    a4 = -1.453152027
    a5 = 1.061405429
    p = 0.3275911

    sign = 1.0 if x >= 0 else -1.0
    x_abs = abs(x) / math.sqrt(2.0)

    t = 1.0 / (1.0 + p * x_abs)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x_abs * x_abs)

    return 0.5 * (1.0 + sign * y)


def norm_pdf(x):
    """Probability density function for the standard normal distribution."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_ticker(ticker):
    """Check that a ticker string looks reasonable."""
    if not ticker or not isinstance(ticker, str):
        return False
    cleaned = ticker.strip().upper()
    return 1 <= len(cleaned) <= 6 and cleaned.isalpha()


def validate_date(date_str, fmt="%Y-%m-%d"):
    """Parse an ISO-format date string and return a date object, or None."""
    try:
        return datetime.strptime(date_str, fmt).date()
    except (ValueError, TypeError):
        return None


def days_to_expiry(expiration_date):
    """Return the number of calendar days until *expiration_date*."""
    if isinstance(expiration_date, str):
        expiration_date = validate_date(expiration_date)
    if expiration_date is None:
        return None
    delta = expiration_date - date.today()
    return max(delta.days, 0)


def years_to_expiry(expiration_date):
    """Return time to expiry as a fraction of a year (365.25 days)."""
    dte = days_to_expiry(expiration_date)
    if dte is None:
        return None
    return max(dte / 365.25, 1 / 365.25)  # floor at 1 day to avoid /0


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_currency(value):
    """Format a number as $X.XX."""
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def format_percentage(value):
    """Format a decimal as X.X% (e.g. 0.085 -> '8.5%')."""
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def normalize_score(value, min_val, max_val):
    """Normalize *value* to a 0-100 scale given [min_val, max_val]."""
    if max_val == min_val:
        return 50.0
    clamped = max(min_val, min(max_val, value))
    return ((clamped - min_val) / (max_val - min_val)) * 100.0
