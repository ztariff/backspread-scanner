"""
Black-Scholes option pricing and Greeks calculator.
Uses custom normal distribution approximations — no scipy dependency.
"""

import math
from utils import norm_cdf, norm_pdf


class BlackScholesCalculator:
    """
    Compute option prices and Greeks using the Black-Scholes-Merton model.

    Parameters
    ----------
    S : float – current underlying price
    K : float – strike price
    T : float – time to expiry in years
    r : float – risk-free rate (annualized, e.g. 0.045 for 4.5%)
    sigma : float – implied volatility (annualized, e.g. 0.25 for 25%)
    option_type : str – "call" or "put"
    """

    def __init__(self, S, K, T, r, sigma, option_type="call"):
        self.S = float(S)
        self.K = float(K)
        self.T = max(float(T), 1e-10)  # avoid division by zero
        self.r = float(r)
        self.sigma = max(float(sigma), 1e-10)
        self.option_type = option_type.lower()

        # Pre-compute d1, d2
        self._d1 = self._calc_d1()
        self._d2 = self._d1 - self.sigma * math.sqrt(self.T)

    # ------------------------------------------------------------------
    # Core d1 / d2
    # ------------------------------------------------------------------

    def _calc_d1(self):
        numerator = (
            math.log(self.S / self.K)
            + (self.r + 0.5 * self.sigma ** 2) * self.T
        )
        denominator = self.sigma * math.sqrt(self.T)
        return numerator / denominator

    @property
    def d1(self):
        return self._d1

    @property
    def d2(self):
        return self._d2

    # ------------------------------------------------------------------
    # Option price
    # ------------------------------------------------------------------

    def price(self):
        """Theoretical option price."""
        if self.option_type == "call":
            return (
                self.S * norm_cdf(self._d1)
                - self.K * math.exp(-self.r * self.T) * norm_cdf(self._d2)
            )
        else:
            return (
                self.K * math.exp(-self.r * self.T) * norm_cdf(-self._d2)
                - self.S * norm_cdf(-self._d1)
            )

    # ------------------------------------------------------------------
    # Greeks
    # ------------------------------------------------------------------

    def delta(self):
        """Option delta."""
        if self.option_type == "call":
            return norm_cdf(self._d1)
        else:
            return norm_cdf(self._d1) - 1.0

    def gamma(self):
        """Option gamma (same for calls and puts)."""
        return norm_pdf(self._d1) / (self.S * self.sigma * math.sqrt(self.T))

    def vega(self):
        """Option vega — price change per 1-point (100%) IV change.
        Divide by 100 for per-1% change."""
        return self.S * norm_pdf(self._d1) * math.sqrt(self.T)

    def vega_pct(self):
        """Vega per 1% change in IV (more practical)."""
        return self.vega() / 100.0

    def theta(self):
        """Option theta — daily time decay (per calendar day)."""
        common = -(self.S * norm_pdf(self._d1) * self.sigma) / (
            2.0 * math.sqrt(self.T)
        )
        if self.option_type == "call":
            annual = common - self.r * self.K * math.exp(-self.r * self.T) * norm_cdf(self._d2)
        else:
            annual = common + self.r * self.K * math.exp(-self.r * self.T) * norm_cdf(-self._d2)
        return annual / 365.0  # per calendar day

    def rho(self):
        """Option rho."""
        if self.option_type == "call":
            return (
                self.K * self.T * math.exp(-self.r * self.T) * norm_cdf(self._d2) / 100.0
            )
        else:
            return (
                -self.K * self.T * math.exp(-self.r * self.T) * norm_cdf(-self._d2) / 100.0
            )

    def all_greeks(self):
        """Return a dict of all Greeks."""
        return {
            "delta": self.delta(),
            "gamma": self.gamma(),
            "vega": self.vega_pct(),
            "theta": self.theta(),
            "rho": self.rho(),
        }


# ======================================================================
# Implied-volatility solver
# ======================================================================

def implied_volatility(market_price, S, K, T, r, option_type="call",
                       tol=1e-6, max_iter=100):
    """
    Solve for implied volatility using Newton-Raphson.

    Parameters
    ----------
    market_price : float – observed option price (mid-price recommended)
    S, K, T, r   : Black-Scholes inputs
    option_type   : "call" or "put"
    tol           : convergence tolerance
    max_iter      : maximum iterations

    Returns
    -------
    float – implied volatility, or None if solver fails
    """
    if market_price <= 0:
        return None

    # Brenner-Subrahmanyam initial guess
    sigma = math.sqrt(2.0 * math.pi / max(T, 1e-10)) * (market_price / S)
    sigma = max(min(sigma, 5.0), 0.01)  # clamp to reasonable range

    for _ in range(max_iter):
        bs = BlackScholesCalculator(S, K, T, r, sigma, option_type)
        price_diff = bs.price() - market_price
        v = bs.vega()

        if abs(v) < 1e-12:
            # Vega too small — try a nudge
            sigma += 0.01
            continue

        sigma_new = sigma - price_diff / v
        sigma_new = max(min(sigma_new, 5.0), 0.001)  # clamp

        if abs(sigma_new - sigma) < tol:
            return sigma_new
        sigma = sigma_new

    # Did not converge — return best guess if close
    bs = BlackScholesCalculator(S, K, T, r, sigma, option_type)
    if abs(bs.price() - market_price) / max(market_price, 0.01) < 0.05:
        return sigma
    return None


# ======================================================================
# Convenience functions
# ======================================================================

def calculate_greeks(S, K, T, r, sigma, option_type="call"):
    """One-shot Greeks calculation."""
    bs = BlackScholesCalculator(S, K, T, r, sigma, option_type)
    return bs.all_greeks()


def option_price(S, K, T, r, sigma, option_type="call"):
    """One-shot option price."""
    bs = BlackScholesCalculator(S, K, T, r, sigma, option_type)
    return bs.price()
