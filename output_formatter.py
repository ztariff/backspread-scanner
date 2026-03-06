"""
Output formatting for diagonal ratio backspread scan results.
Terminal tables, CSV, JSON, and detailed analysis views.
"""

import csv
import json
import logging
from typing import List

from diagonal_constructor import DiagonalBackspread
from cheapness_analyzer import CheapnessReport

logger = logging.getLogger("backspread_scanner.output")


def format_table(strategies: List[DiagonalBackspread]) -> str:
    """Format strategies as a terminal table."""
    if not strategies:
        return "No opportunities found."

    try:
        from tabulate import tabulate
        return _format_with_tabulate(strategies)
    except ImportError:
        return _format_plain(strategies)


def _format_with_tabulate(strategies: List[DiagonalBackspread]) -> str:
    from tabulate import tabulate

    headers = [
        "#", "Ticker", "Dir", "Long Leg", "Short Leg",
        "Ratio", "Net $", "Cheap", "Eq.Ratio",
        "Tail $", "Delta", "Vega", "Theta", "Score",
    ]

    rows = []
    for i, s in enumerate(strategies, 1):
        d = s.summary_dict()

        long_str = (
            f"${d['long_strike']:.0f} {d['long_exp'][-5:]}"
            f" @${d['long_price']:.2f} ×{d['long_qty']}"
        )
        short_str = (
            f"${d['short_strike']:.0f} {d['short_exp'][-5:]}"
            f" @${d['short_price']:.2f} ×{d['short_qty']}"
        )

        rows.append([
            i,
            d["ticker"],
            d["direction"][0].upper(),
            long_str,
            short_str,
            d["ratio"],
            f"${d['net_premium']:,.0f}",
            f"{d['cheapness']:.0f}",
            f"{d['equidist_ratio']:.1f}×",
            f"${d['tail_payoff']:,.0f}" if d["tail_payoff"] else "N/A",
            f"{d['net_delta']:.0f}",
            f"{d['net_vega']:.0f}",
            f"{d['net_theta']:.2f}",
            f"{d['score']:.1f}",
        ])

    return tabulate(rows, headers=headers, tablefmt="grid")


def _format_plain(strategies: List[DiagonalBackspread]) -> str:
    lines = []
    header = (
        f"{'#':>3} {'Ticker':<6} {'Dir':<3} {'Long Leg':<22} {'Short Leg':<22} "
        f"{'Ratio':<6} {'Net $':>8} {'Cheap':>5} {'Eq.R':>5} "
        f"{'Tail $':>9} {'Score':>6}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for i, s in enumerate(strategies, 1):
        d = s.summary_dict()
        long_str = f"${d['long_strike']:.0f} {d['long_exp'][-5:]} ×{d['long_qty']}"
        short_str = f"${d['short_strike']:.0f} {d['short_exp'][-5:]} ×{d['short_qty']}"

        lines.append(
            f"{i:>3} {d['ticker']:<6} {d['direction'][0].upper():<3} "
            f"{long_str:<22} {short_str:<22} "
            f"{d['ratio']:<6} ${d['net_premium']:>7,.0f} "
            f"{d['cheapness']:>5.0f} {d['equidist_ratio']:>4.1f}× "
            f"${d.get('tail_payoff', 0):>8,.0f} {d['score']:>6.1f}"
        )

    return "\n".join(lines)


def format_detailed(strategy: DiagonalBackspread) -> str:
    """Detailed multi-section analysis of a single strategy."""
    d = strategy.summary_dict()
    dir_label = "CALL" if strategy.direction == "call" else "PUT"
    arrow = "↑" if strategy.direction == "call" else "↓"

    lines = [
        f"{'═'*65}",
        f"  {d['ticker']} DIAGONAL {dir_label} BACKSPREAD {arrow}  (Score: {d['score']:.1f})",
        f"{'═'*65}",
        f"  Underlying: ${strategy.underlying_price:.2f}",
        f"",
        f"  ┌─ LONG LEG (convexity) ─────────────────────────────┐",
        f"  │  {strategy.long_qty}× {strategy.direction} ${strategy.long_leg.strike:.2f}",
        f"  │  Expiry: {strategy.long_leg.expiration}",
        f"  │  Price:  ${strategy.long_leg.entry_price:.2f} per contract",
        f"  │  Total:  ${strategy.long_leg.total_cost:,.2f}",
        f"  │  IV:     {strategy.long_leg.contract.implied_volatility*100:.1f}%" if strategy.long_leg.contract.implied_volatility else f"  │  IV:     N/A",
        f"  └─────────────────────────────────────────────────────┘",
        f"",
        f"  ┌─ SHORT LEG (financing) ────────────────────────────┐",
        f"  │  {strategy.short_qty}× {strategy.direction} ${strategy.short_leg.strike:.2f}",
        f"  │  Expiry: {strategy.short_leg.expiration}",
        f"  │  Price:  ${strategy.short_leg.entry_price:.2f} per contract",
        f"  │  Credit: ${abs(strategy.short_leg.total_cost):,.2f}",
        f"  │  IV:     {strategy.short_leg.contract.implied_volatility*100:.1f}%" if strategy.short_leg.contract.implied_volatility else f"  │  IV:     N/A",
        f"  └─────────────────────────────────────────────────────┘",
        f"",
        f"  Net Premium: ${d['net_premium']:,.2f}  "
        f"({'CREDIT' if strategy.net_premium < 0 else 'DEBIT'})",
        f"  Premium Neutrality: {d['premium_neutral_pct']:.1f}% deviation",
        f"  Ratio: {d['ratio']} (long:short)",
        f"",
        f"  ── Cheapness Metrics ──",
        f"  Composite Cheapness Score: {d['cheapness']:.1f}/100",
        f"  Equidistant Ratio: {d['equidist_ratio']:.1f}× "
        f"(opposite-side option is {d['equidist_ratio']:.1f}× more expensive)",
    ]

    if d['iv_rv'] > 0:
        lines.append(f"  IV/RV Ratio: {d['iv_rv']:.2f} "
                      f"({'underpriced' if d['iv_rv'] < 1 else 'fairly priced'})")

    if d['hist_move_yield'] > 0:
        lines.append(f"  Historical Move Yield: {d['hist_move_yield']:.0f}× "
                      f"(if max past move repeats)")

    lines.extend([
        f"",
        f"  ── Tail Scenario ──",
        f"  If max historical move repeats: ${d['tail_payoff']:,.0f} P&L" if d['tail_payoff'] else "  Tail payoff: N/A",
        f"",
        f"  ── Greeks (at entry) ──",
        f"  Delta: {d['net_delta']:+.1f}",
        f"  Vega:  {d['net_vega']:+.1f}  (benefits from vol expansion)",
        f"  Theta: {d['net_theta']:+.2f}  ($/day carrying cost)",
        f"{'═'*65}",
    ])

    return "\n".join(lines)


def format_cheapness_report(reports: List[CheapnessReport], top_n: int = 20) -> str:
    """Format cheapness analysis results."""
    if not reports:
        return "No cheap options found."

    lines = [
        f"  CHEAPEST FAR-OTM OPTIONS",
        f"  {'─'*55}",
    ]

    for i, r in enumerate(reports[:top_n], 1):
        c = r.contract
        direction = "↑" if c.option_type == "call" else "↓"
        otm_pct = r.otm_distance_pct * 100

        eq_str = f"Eq:{r.equidistant_ratio:.1f}×" if r.equidistant_ratio else "Eq:N/A"
        iv_str = f"IV/RV:{r.iv_rv_ratio:.2f}" if r.iv_rv_ratio else "IV/RV:N/A"
        mv_str = f"Yield:{r.move_yield_ratio:.0f}×" if r.move_yield_ratio else "Yield:N/A"

        lines.append(
            f"  {i:>2}. {c.ticker} {c.option_type.upper()} ${c.strike:.0f} "
            f"({otm_pct:+.0f}% OTM{direction}) "
            f"@ ${r.option_price_dollars:.2f}  "
            f"Score:{r.composite_cheapness:.0f}  "
            f"{eq_str}  {iv_str}  {mv_str}"
        )

    return "\n".join(lines)


# ------------------------------------------------------------------
# File export
# ------------------------------------------------------------------

def export_csv(strategies: List[DiagonalBackspread], filepath: str):
    if not strategies:
        return

    rows = [s.summary_dict() for s in strategies]
    fieldnames = list(rows[0].keys())

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"Exported {len(rows)} strategies to {filepath}")


def export_json(strategies: List[DiagonalBackspread], filepath: str):
    data = [s.summary_dict() for s in strategies]
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info(f"Exported {len(data)} strategies to {filepath}")
