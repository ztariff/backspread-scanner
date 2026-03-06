#!/usr/bin/env python3
"""
Ratio Backspread Scanner
=========================
Scans for cheap far-OTM options across a broad universe, then constructs
premium-neutral ratio backspreads using shorter-dated (or same-expiry)
ATM-ish options as financing.

Automatically detects which side of the chain (calls or puts) is cheap —
no need to specify direction.

Supports both diagonal (different expiry) and same-expiry (0DTE) structures.

Think Taleb on Eurodollar calls, 1987.

Usage:
    python scanner.py                                  # scan default universe
    python scanner.py --tickers SPY,QQQ                # specific tickers
    python scanner.py --universe etfs --show-cheapness  # ETFs with cheapness report
    python scanner.py --tickers AAPL --format detailed -v
"""

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import Config
from polygon_client import PolygonClient, PolygonAPIError
from option_chain import OptionChain
from cheapness_analyzer import CheapnessAnalyzer
from diagonal_constructor import build_diagonal_backspreads, DiagonalBackspread
from opportunity_ranker import OpportunityRanker
from output_formatter import (
    format_table,
    format_detailed,
    format_cheapness_report,
    export_csv,
    export_json,
)
from skew_analyzer import SkewAnalyzer
from utils import setup_logging, validate_ticker, validate_date, days_to_expiry

logger = logging.getLogger("backspread_scanner")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scan for ratio backspread opportunities on cheap far-OTM options.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Universe — now optional; defaults to config.default_tickers
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--tickers", "-t",
        help="Comma-separated tickers or path to file (one per line)",
    )
    group.add_argument(
        "--universe", "-u",
        choices=["etfs", "broad", "custom"],
        help="Pre-built universe: 'etfs' (major ETFs/indices), "
             "'broad' (all US equities from Polygon)",
    )

    # Expiration control
    parser.add_argument(
        "--long-expiry",
        help="Specific long-leg expiration (YYYY-MM-DD). "
             "If omitted, auto-selects within config DTE range.",
    )
    parser.add_argument(
        "--short-expiry",
        help="Specific short-leg expiration (YYYY-MM-DD). "
             "If omitted, auto-selects nearest weekly/monthly.",
    )

    # Cheapness filters
    parser.add_argument(
        "--max-price", type=float, default=None,
        help="Max option price for the long leg (default: $5.00)",
    )
    parser.add_argument(
        "--min-otm", type=float, default=None,
        help="Min %% OTM for long leg (e.g. 0.10 = 10%% OTM, default: 5%%)",
    )
    parser.add_argument(
        "--max-otm", type=float, default=None,
        help="Max %% OTM for long leg (default: 40%%)",
    )
    parser.add_argument(
        "--min-cheapness", type=float, default=20.0,
        help="Minimum cheapness score to display (0-100, default: 20)",
    )

    # Output
    parser.add_argument("--output", "-o", help="Output file (CSV or JSON)")
    parser.add_argument(
        "--format", "-f",
        choices=["table", "csv", "json", "detailed"],
        default="table",
    )
    parser.add_argument("--limit", "-n", type=int, default=None)
    parser.add_argument("--show-cheapness", action="store_true",
                        help="Show cheapness report before trade construction")
    parser.add_argument("--show-skew", action="store_true",
                        help="Show skew analysis for each chain")
    parser.add_argument("--verbose", "-v", action="store_true")

    return parser.parse_args()


def resolve_tickers(args, config: Config, client: PolygonClient):
    """Resolve the ticker list from args, defaulting to config.default_tickers."""
    if args.tickers:
        if os.path.isfile(args.tickers):
            with open(args.tickers) as f:
                tickers = [
                    line.strip().upper()
                    for line in f if line.strip() and not line.startswith("#")
                ]
        else:
            tickers = [t.strip().upper() for t in args.tickers.split(",")]
        return [t for t in tickers if validate_ticker(t)]

    elif args.universe == "etfs":
        return client.get_index_and_etf_tickers()
    elif args.universe == "broad":
        logger.info("Fetching broad US equity universe from Polygon...")
        return client.get_sp500_tickers()
    else:
        # Default: use curated ticker list from config
        return list(config.default_tickers)


def resolve_expirations(args, config: Config, client: PolygonClient, ticker: str):
    """
    Resolve short and long expiration dates.
    Returns (short_exps, long_exps).

    Supports 0DTE same-expiry: short and long exps can overlap.
    """
    today = date.today()

    if args.short_expiry:
        short_exps = [args.short_expiry]
    else:
        # Find nearest expirations within short DTE range
        all_exps = client.get_expirations(
            ticker, min_dte=config.short_min_dte, max_dte=config.short_max_dte
        )
        short_exps = all_exps[:3] if all_exps else []

        # Fallback: generate dates (include today for 0DTE)
        if not short_exps:
            # Check today first (0DTE)
            if config.short_min_dte == 0:
                short_exps.append(today.isoformat())
            for days_ahead in range(max(1, config.short_min_dte), config.short_max_dte + 1):
                exp_date = today + timedelta(days=days_ahead)
                if exp_date.weekday() == 4:  # Friday
                    short_exps.append(exp_date.isoformat())
                    if len(short_exps) >= 3:
                        break

    if args.long_expiry:
        long_exps = [args.long_expiry]
    else:
        all_exps = client.get_expirations(
            ticker, min_dte=config.long_min_dte, max_dte=config.long_max_dte
        )

        # For 0DTE support: if long_min_dte is 0, include today
        if config.long_min_dte == 0 and all_exps and all_exps[0] == today.isoformat():
            # Keep today in the list — enables same-expiry backspreads
            pass

        # Pick a few spread across the range
        if len(all_exps) >= 3:
            long_exps = [all_exps[0], all_exps[len(all_exps)//2], all_exps[-1]]
        else:
            long_exps = all_exps[:3]

        # Fallback
        if not long_exps:
            if config.long_min_dte == 0:
                long_exps.append(today.isoformat())
            for months_ahead in [1, 2, 3]:
                m = today.month + months_ahead
                y = today.year + (m - 1) // 12
                m = ((m - 1) % 12) + 1
                first = date(y, m, 1)
                days_to_fri = (4 - first.weekday()) % 7
                third_friday = first + timedelta(days=days_to_fri + 14)
                long_exps.append(third_friday.isoformat())

    return short_exps, long_exps


def scan_ticker(client, ticker, config, args, ranker):
    """
    Full scan of one ticker:
      1. Fetch historical data (realized vol, max moves)
      2. Resolve expirations
      3. Fetch option chains
      4. Run cheapness analysis on long-dated chain (BOTH calls and puts)
      5. Find financing on short-dated chain
      6. Build ratio backspreads
      7. Score and rank
    """
    logger.info(f"{'─'*40}")
    logger.info(f"Scanning {ticker}...")

    # Step 1: Historical context
    price = client.get_stock_price(ticker)
    if not price or price <= 0:
        logger.warning(f"Could not get price for {ticker}, skipping")
        return [], []

    realized_vol = client.get_realized_vol(ticker, config.realized_vol_lookback)
    max_moves = client.get_max_moves(ticker, config.max_move_lookback)

    if realized_vol:
        logger.info(f"  {ticker} @ ${price:.2f}  RV={realized_vol*100:.1f}%")
    else:
        logger.info(f"  {ticker} @ ${price:.2f}  RV=N/A")

    if max_moves:
        logger.info(
            f"  Max moves: up {max_moves.get('max_up_pct', 0)*100:+.1f}%  "
            f"down {max_moves.get('max_down_pct', 0)*100:.1f}%"
        )

    # Step 2: Resolve expirations
    short_exps, long_exps = resolve_expirations(args, config, client, ticker)

    if not short_exps or not long_exps:
        logger.warning(f"  No valid expirations for {ticker}")
        return [], []

    logger.info(f"  Short expirations: {short_exps}")
    logger.info(f"  Long expirations:  {long_exps}")

    all_strategies = []
    all_cheap_reports = []

    # Step 3-7: For each long expiry, find cheap options and pair with short expiry
    for long_exp in long_exps:
        try:
            long_chain = client.get_option_chain(ticker, long_exp, price)
        except Exception as e:
            logger.warning(f"  Failed to fetch long chain {long_exp}: {e}")
            continue

        if not long_chain.calls and not long_chain.puts:
            continue

        # Optional skew analysis
        if args.show_skew:
            analyzer = SkewAnalyzer(long_chain, risk_free_rate=config.risk_free_rate)
            skew = analyzer.analyze()
            print(f"\n{skew.ticker} exp={long_exp}:")
            if skew.put_skew_absolute is not None:
                print(f"  Put skew (25d): {skew.put_skew_absolute*100:+.1f}%")
            if skew.call_skew_absolute is not None:
                print(f"  Call skew (25d): {skew.call_skew_absolute*100:+.1f}%")

        # Cheapness analysis — always scan BOTH calls and puts
        cheapness = CheapnessAnalyzer(
            long_chain,
            realized_vol=realized_vol,
            max_moves=max_moves,
            risk_free_rate=config.risk_free_rate,
        )

        max_price = args.max_price or config.long_max_price

        cheap_reports = cheapness.find_cheap_options(
            option_type="both",       # always scan both sides
            max_delta=config.long_max_delta,
            min_delta=getattr(config, 'long_min_delta', 0.02),
            max_price=max_price,
            min_score=args.min_cheapness,
        )

        all_cheap_reports.extend(cheap_reports)

        if not cheap_reports:
            logger.debug(f"  No cheap options found on {long_exp}")
            continue

        logger.info(f"  Found {len(cheap_reports)} cheap options on {long_exp}")

        # For each short expiry, build trades
        for short_exp in short_exps:
            # For same-expiry backspreads: the short chain IS the long chain
            if short_exp == long_exp:
                short_chain = long_chain
            else:
                try:
                    short_chain = client.get_option_chain(ticker, short_exp, price)
                except Exception as e:
                    logger.warning(f"  Failed to fetch short chain {short_exp}: {e}")
                    continue

            if not short_chain.calls and not short_chain.puts:
                continue

            # Populate deltas on short chain if missing
            from skew_analyzer import SkewAnalyzer as SA
            sa = SA(short_chain, risk_free_rate=config.risk_free_rate)
            sa._populate_ivs()
            sa._populate_deltas()

            strategies = build_diagonal_backspreads(
                cheap_reports, short_chain, config,
            )

            for s in strategies:
                ranker.score(s)

            all_strategies.extend(strategies)

            if strategies:
                label = "same-expiry" if short_exp == long_exp else "diagonal"
                logger.info(
                    f"  Built {len(strategies)} {label} backspreads: "
                    f"long={long_exp} short={short_exp}"
                )

    return all_strategies, all_cheap_reports


def main():
    args = parse_args()
    setup_logging(args.verbose)

    config = Config.from_env()
    errors = config.validate()

    if errors:
        for e in errors:
            print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    client = PolygonClient(config.polygon_api_key, config.rate_limit_pause)
    ranker = OpportunityRanker()

    # Resolve universe
    tickers = resolve_tickers(args, config, client)
    if not tickers:
        print("No valid tickers.", file=sys.stderr)
        sys.exit(1)

    print(f"Ratio Backspread Scanner")
    print(f"{'='*50}")
    print(f"Universe: {len(tickers)} ticker(s): {', '.join(tickers[:10])}"
          + (f" + {len(tickers)-10} more" if len(tickers) > 10 else ""))
    print(f"Scanning: calls & puts (auto-detect cheapest side)")
    print(f"Long leg: {config.long_min_otm_pct*100:.0f}-{config.long_max_otm_pct*100:.0f}% OTM, "
          f"{config.long_min_dte}-{config.long_max_dte} DTE, max ${config.long_max_price:.2f}")
    print(f"Short leg: delta {config.short_min_delta:.2f}-{config.short_max_delta:.2f}, "
          f"{config.short_min_dte}-{config.short_max_dte} DTE")
    if config.short_min_dte == 0 and config.long_min_dte == 0:
        print(f"0DTE: same-expiry backspreads enabled")
    print()

    # Scan
    all_strategies = []
    all_cheap = []

    for ticker in tickers:
        try:
            strats, cheap = scan_ticker(client, ticker, config, args, ranker)
            all_strategies.extend(strats)
            all_cheap.extend(cheap)
        except PolygonAPIError as e:
            logger.error(f"API error on {ticker}: {e}")
            continue
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            continue

    # Show cheapness report if requested
    if args.show_cheapness and all_cheap:
        print(f"\n{'='*60}")
        print(format_cheapness_report(all_cheap, top_n=30))
        print()

    # Rank globally
    limit = args.limit or config.top_n
    ranked = ranker.rank(all_strategies, top_n=limit)

    if not ranked:
        print("\nNo ratio backspread opportunities found matching your criteria.")
        print("Try: wider OTM range (--min-otm 0.03), higher max price (--max-price 10), ")
        print("     or lower cheapness threshold (--min-cheapness 10)")
        return

    # Output
    print(f"\n{'='*60}")
    print(f"  TOP {len(ranked)} RATIO BACKSPREADS")
    print(f"{'='*60}\n")

    if args.format == "detailed":
        for s in ranked:
            print(format_detailed(s))
            print()
    else:
        print(format_table(ranked))

    # File export
    if args.output:
        ext = Path(args.output).suffix.lower()
        if ext == ".json":
            export_json(ranked, args.output)
        else:
            export_csv(ranked, args.output)
        print(f"\nResults exported to {args.output}")

    # Summary
    print(f"\nSummary:")
    print(f"  Tickers scanned: {len(tickers)}")
    print(f"  Cheap options found: {len(all_cheap)}")
    print(f"  Strategies evaluated: {len(all_strategies)}")
    if ranked:
        best = ranked[0]
        same_exp = best.long_expiry == best.short_expiry
        type_label = "same-expiry" if same_exp else "diagonal"
        print(f"  Best opportunity: {best.ticker} {best.direction} "
              f"${best.long_leg.strike:.0f}/{best.short_leg.strike:.0f} "
              f"({type_label}, score {best.score:.1f})")


if __name__ == "__main__":
    main()
