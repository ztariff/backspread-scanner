"""
CME Globex Cheap Options Scanner
Scans across major futures products for cheap, liquid OTM options
suitable for Taleb-style backspread strategies.

Scoring: 5-dimension cheapness model
  1. Equidistant Comparison (30%) — put vs call skew at same OTM distance
  2. Historical Moves (25%) — convexity-weighted tail payoff potential
  3. IV vs RV (20%) — wing implied vol vs realized vol disconnect
  4. Wing Loading (15%) — how starved are the wings of premium
  5. Absolute Cheapness (10%) — raw price level

Filters:
  - 3-6 month expiry
  - OTM only (puts below spot, calls above spot)
  - Minimum open interest / volume for liquidity
  - Any ATR distance acceptable (even 10-20 ATRs)

Run: pip3 install databento && python3 scan_globex.py
"""

import json
import sys
import math
from datetime import datetime, timedelta

try:
    import databento as db
except ImportError:
    print("Install databento first: pip3 install databento --break-system-packages")
    sys.exit(1)

DATABENTO_KEY = "db-qsqvF3QpT7mr6M75DyQC5N33NcTV5"
DATASET = "GLBX.MDP3"
TODAY = datetime.now().strftime("%Y-%m-%d")

# ──────────────────────────────────────────────────────────────
# PRODUCT DEFINITIONS
# Each product: symbol root, contract months to scan (3-6mo out),
# strike_divisor (to convert raw strike to price), tick info
# ──────────────────────────────────────────────────────────────

# From March 2026, 3-6 months out = June-September 2026
# Month codes: H=Mar, M=Jun, N=Jul, Q=Aug, U=Sep, V=Oct, Z=Dec
# Year: 6 = 2026

PRODUCTS = [
    # Equity Index Futures (quarterly: H, M, U, Z)
    {"root": "ES",  "name": "E-mini S&P 500",     "months": ["M6", "U6"], "strike_div": 1,    "tick": 0.25},
    {"root": "NQ",  "name": "E-mini Nasdaq 100",   "months": ["M6", "U6"], "strike_div": 1,    "tick": 0.25},
    {"root": "RTY", "name": "E-mini Russell 2000",  "months": ["M6", "U6"], "strike_div": 1,    "tick": 0.1},
    {"root": "YM",  "name": "E-mini Dow",           "months": ["M6", "U6"], "strike_div": 1,    "tick": 1},

    # Energy Futures (monthly)
    {"root": "CL",  "name": "WTI Crude Oil",        "months": ["M6", "N6", "Q6", "U6"], "strike_div": 1, "tick": 0.01},
    {"root": "NG",  "name": "Natural Gas",           "months": ["M6", "N6", "Q6", "U6"], "strike_div": 1, "tick": 0.001},
    {"root": "HO",  "name": "Heating Oil",           "months": ["M6", "N6", "Q6", "U6"], "strike_div": 1, "tick": 0.0001},
    {"root": "RB",  "name": "RBOB Gasoline",         "months": ["M6", "N6", "Q6", "U6"], "strike_div": 1, "tick": 0.0001},

    # Metals (specific months)
    {"root": "GC",  "name": "Gold",                  "months": ["M6", "Q6"], "strike_div": 1, "tick": 0.1},
    {"root": "SI",  "name": "Silver",                "months": ["N6", "U6"], "strike_div": 1, "tick": 0.005},
    {"root": "HG",  "name": "Copper",                "months": ["N6", "U6"], "strike_div": 1, "tick": 0.0005},

    # Treasury Futures (quarterly: H, M, U, Z)
    {"root": "ZB",  "name": "30Y Treasury Bond",    "months": ["M6", "U6"], "strike_div": 1, "tick": 0.015625},
    {"root": "ZN",  "name": "10Y Treasury Note",    "months": ["M6", "U6"], "strike_div": 1, "tick": 0.015625},
    {"root": "ZF",  "name": "5Y Treasury Note",     "months": ["M6", "U6"], "strike_div": 1, "tick": 0.0078125},

    # SOFR (quarterly)
    {"root": "SR3", "name": "3M SOFR",              "months": ["M6", "U6"], "strike_div": 100, "tick": 0.0025},

    # FX Futures (quarterly: H, M, U, Z)
    {"root": "6E",  "name": "Euro FX",              "months": ["M6", "U6"], "strike_div": 1, "tick": 0.0001},
    {"root": "6J",  "name": "Japanese Yen",         "months": ["M6", "U6"], "strike_div": 1, "tick": 0.0000005},
    {"root": "6B",  "name": "British Pound",        "months": ["M6", "U6"], "strike_div": 1, "tick": 0.0001},

    # Ags (specific months)
    {"root": "ZC",  "name": "Corn",                 "months": ["N6", "U6"], "strike_div": 1, "tick": 0.125},
    {"root": "ZS",  "name": "Soybeans",             "months": ["N6", "U6"], "strike_div": 1, "tick": 0.125},
    {"root": "ZW",  "name": "Wheat",                "months": ["N6", "U6"], "strike_div": 1, "tick": 0.125},
]


def records_to_list(dbn_store):
    results = []
    try:
        for rec in dbn_store:
            results.append(rec)
    except Exception as e:
        pass
    return results


def safe_float(val):
    if val is None:
        return None
    v = float(val)
    if abs(v) > 1e6:
        return v / 1e9
    return v


def compute_atr(bars, period=14):
    """Compute ATR from daily OHLCV bars."""
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h = bars[i]["high"]
        l = bars[i]["low"]
        pc = bars[i-1]["close"]
        if h is None or l is None or pc is None:
            continue
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if len(trs) < period:
        return None
    # Use last `period` TRs
    return sum(trs[-period:]) / period


def compute_rv(bars, period=20):
    """Compute annualized realized volatility from daily closes."""
    closes = [b["close"] for b in bars if b["close"] is not None]
    if len(closes) < period + 1:
        return None
    returns = []
    for i in range(1, len(closes)):
        if closes[i-1] > 0:
            returns.append(math.log(closes[i] / closes[i-1]))
    if len(returns) < period:
        return None
    recent = returns[-period:]
    mean = sum(recent) / len(recent)
    var = sum((r - mean) ** 2 for r in recent) / (len(recent) - 1)
    daily_vol = math.sqrt(var)
    return daily_vol * math.sqrt(252)


def compute_max_moves(bars, window=20):
    """Compute max up and down moves over rolling windows."""
    closes = [b["close"] for b in bars if b["close"] is not None]
    if len(closes) < window + 1:
        return None, None
    max_down = 0
    max_up = 0
    for i in range(window, len(closes)):
        move = closes[i] - closes[i - window]
        if move < max_down:
            max_down = move
        if move > max_up:
            max_up = move
    return abs(max_down), max_up


def score_option(opt, underlying_price, atr, rv, max_down_20d, max_up_20d,
                 chain_settlements, strike_div):
    """Score a single option on 5 dimensions. Returns dict with scores."""
    strike_raw = opt.get("strike", 0)
    strike_price = strike_raw / strike_div if strike_div != 1 else strike_raw
    settlement = opt.get("settlement", 0)
    opt_type = opt.get("type", "")

    if settlement is None or settlement <= 0:
        return None
    if underlying_price is None or underlying_price <= 0:
        return None

    # OTM distance
    if opt_type == "put":
        otm_dist = underlying_price - strike_price
    else:
        otm_dist = strike_price - underlying_price

    if otm_dist <= 0:
        return None  # ITM, skip

    atrs_otm = otm_dist / atr if atr and atr > 0 else None

    # ────────────────────────────────────────────
    # 1. EQUIDISTANT COMPARISON (30%)
    # ────────────────────────────────────────────
    equidist_score = 50  # default
    if opt_type == "put":
        # Find equidistant call
        target_call_strike = underlying_price + otm_dist
        equidist_call_settle = interpolate_settlement(
            chain_settlements, "call", target_call_strike * strike_div, strike_div)
        if equidist_call_settle and equidist_call_settle > 0:
            ratio = equidist_call_settle / settlement
            # ratio > 1 means put is cheaper than equidistant call
            if ratio >= 20:
                equidist_score = 97
            elif ratio >= 10:
                equidist_score = 92
            elif ratio >= 5:
                equidist_score = 85
            elif ratio >= 3:
                equidist_score = 75
            elif ratio >= 2:
                equidist_score = 65
            elif ratio >= 1.5:
                equidist_score = 55
            else:
                equidist_score = 40
    else:
        # Find equidistant put
        target_put_strike = underlying_price - otm_dist
        equidist_put_settle = interpolate_settlement(
            chain_settlements, "put", target_put_strike * strike_div, strike_div)
        if equidist_put_settle and equidist_put_settle > 0:
            ratio = equidist_put_settle / settlement
            if ratio >= 20:
                equidist_score = 97
            elif ratio >= 10:
                equidist_score = 92
            elif ratio >= 5:
                equidist_score = 85
            elif ratio >= 3:
                equidist_score = 75
            elif ratio >= 2:
                equidist_score = 65
            elif ratio >= 1.5:
                equidist_score = 55
            else:
                equidist_score = 40

    # ────────────────────────────────────────────
    # 2. HISTORICAL MOVES — convexity-weighted (25%)
    # ────────────────────────────────────────────
    hist_score = 50  # default
    max_move = max_down_20d if opt_type == "put" else max_up_20d
    if max_move and max_move > 0:
        # How deep ITM on a 1x, 2x, 3x max move?
        settle_price = settlement / strike_div if strike_div != 1 else settlement

        itm_1x = max(0, max_move - otm_dist)
        itm_2x = max(0, 2 * max_move - otm_dist)
        itm_3x = max(0, 3 * max_move - otm_dist)

        yield_1x = (itm_1x / settle_price) if settle_price > 0 else 0
        yield_2x = (itm_2x / settle_price) if settle_price > 0 else 0
        yield_3x = (itm_3x / settle_price) if settle_price > 0 else 0

        # Score based on convexity potential
        if yield_3x >= 1000:
            hist_score = 100
        elif yield_3x >= 500:
            hist_score = 95
        elif yield_3x >= 200:
            hist_score = 90
        elif yield_3x >= 100:
            hist_score = 85
        elif yield_2x >= 100:
            hist_score = 80
        elif yield_2x >= 50:
            hist_score = 75
        elif yield_1x >= 30:
            hist_score = 70
        elif yield_1x >= 10:
            hist_score = 60
        elif yield_1x > 0:
            hist_score = 50
        else:
            hist_score = 30  # doesn't reach strike even on 1x max move
    else:
        yield_1x = yield_2x = yield_3x = 0

    # ────────────────────────────────────────────
    # 3. IV vs RV (20%)
    # ────────────────────────────────────────────
    iv_rv_score = 50  # default
    if rv and rv > 0 and atr and atr > 0:
        # Approximate: how many sigma OTM based on RV?
        # Use ~105 day horizon (avg of 3-6 months)
        t = 105 / 252
        sigma_move = underlying_price * rv * math.sqrt(t)
        sigmas_otm = otm_dist / sigma_move if sigma_move > 0 else 999

        # At minimum tick with few sigmas OTM = massive IV/RV disconnect
        is_min_tick = (settlement <= 2)  # within 2 ticks of minimum

        if is_min_tick and sigmas_otm < 1:
            iv_rv_score = 97  # extreme mispricing
        elif is_min_tick and sigmas_otm < 2:
            iv_rv_score = 92
        elif is_min_tick and sigmas_otm < 3:
            iv_rv_score = 85
        elif sigmas_otm < 1:
            iv_rv_score = 80
        elif sigmas_otm < 2:
            iv_rv_score = 65
        elif sigmas_otm < 3:
            iv_rv_score = 50
        else:
            iv_rv_score = 35
    else:
        sigmas_otm = None

    # ────────────────────────────────────────────
    # 4. WING LOADING (15%)
    # ────────────────────────────────────────────
    wing_score = 50  # default
    same_type_settles = [s for s in chain_settlements if s["type"] == opt_type and s["settlement"] and s["settlement"] > 0]
    if same_type_settles:
        total_premium = sum(s["settlement"] for s in same_type_settles)
        # "Wing" = options at or beyond our strike
        if opt_type == "put":
            wing_premium = sum(s["settlement"] for s in same_type_settles if s["strike"] <= strike_raw)
        else:
            wing_premium = sum(s["settlement"] for s in same_type_settles if s["strike"] >= strike_raw)

        wing_pct = wing_premium / total_premium if total_premium > 0 else 0

        # Lower wing loading = cheaper wings = higher score
        if wing_pct < 0.01:
            wing_score = 97
        elif wing_pct < 0.03:
            wing_score = 92
        elif wing_pct < 0.05:
            wing_score = 85
        elif wing_pct < 0.10:
            wing_score = 75
        elif wing_pct < 0.20:
            wing_score = 60
        else:
            wing_score = 45

    # ────────────────────────────────────────────
    # 5. ABSOLUTE CHEAPNESS (10%)
    # ────────────────────────────────────────────
    settle_price = settlement / strike_div if strike_div != 1 else settlement
    pct_of_underlying = settle_price / underlying_price if underlying_price > 0 else 1

    if settlement <= 1:  # at or near minimum tick
        abs_score = 100
    elif settlement <= 2:
        abs_score = 95
    elif settlement <= 5:
        abs_score = 85
    elif pct_of_underlying < 0.001:
        abs_score = 80
    elif pct_of_underlying < 0.005:
        abs_score = 65
    elif pct_of_underlying < 0.01:
        abs_score = 50
    else:
        abs_score = 35

    # ────────────────────────────────────────────
    # COMPOSITE
    # ────────────────────────────────────────────
    composite = (
        0.30 * equidist_score +
        0.25 * hist_score +
        0.20 * iv_rv_score +
        0.15 * wing_score +
        0.10 * abs_score
    )

    return {
        "composite": round(composite, 1),
        "equidist": equidist_score,
        "historical": hist_score,
        "iv_rv": iv_rv_score,
        "wing_loading": wing_score,
        "absolute": abs_score,
        "atrs_otm": round(atrs_otm, 1) if atrs_otm else None,
        "sigmas_otm": round(sigmas_otm, 2) if sigmas_otm else None,
        "yield_1x": round(yield_1x, 1) if yield_1x else 0,
        "yield_2x": round(yield_2x, 1) if yield_2x else 0,
        "yield_3x": round(yield_3x, 1) if yield_3x else 0,
    }


def interpolate_settlement(chain_settlements, opt_type, target_strike_raw, strike_div):
    """Find settlement at target strike by interpolation."""
    same_type = sorted(
        [s for s in chain_settlements if s["type"] == opt_type and s["settlement"] and s["settlement"] > 0],
        key=lambda x: x["strike"]
    )
    if not same_type:
        return None

    # Exact match
    for s in same_type:
        if abs(s["strike"] - target_strike_raw) < 0.01:
            return s["settlement"]

    # Interpolate
    for i in range(len(same_type) - 1):
        s1 = same_type[i]
        s2 = same_type[i + 1]
        if s1["strike"] <= target_strike_raw <= s2["strike"]:
            frac = (target_strike_raw - s1["strike"]) / (s2["strike"] - s1["strike"]) if s2["strike"] != s1["strike"] else 0
            return s1["settlement"] + frac * (s2["settlement"] - s1["settlement"])

    return None


def scan_product(client, product):
    """Scan a single product for cheap options."""
    root = product["root"]
    strike_div = product["strike_div"]
    results = []

    for month in product["months"]:
        symbol = f"{root}{month}"
        print(f"\n  Scanning {symbol} ({product['name']})...")

        # ── Pull historical bars ──
        try:
            bars_store = client.timeseries.get_range(
                dataset=DATASET,
                symbols=symbol,
                schema="ohlcv-1d",
                start=(datetime.now() - timedelta(days=300)).strftime("%Y-%m-%d"),
                end=TODAY,
            )
            bars_raw = records_to_list(bars_store)
            bars = []
            for bar in bars_raw:
                try:
                    bars.append({
                        "open": safe_float(getattr(bar, 'open', None)),
                        "high": safe_float(getattr(bar, 'high', None)),
                        "low": safe_float(getattr(bar, 'low', None)),
                        "close": safe_float(getattr(bar, 'close', None)),
                        "volume": getattr(bar, 'volume', None),
                    })
                except:
                    pass

            if not bars or bars[-1]["close"] is None:
                print(f"    No bars for {symbol}, skipping")
                continue

            underlying_price = bars[-1]["close"]
            atr = compute_atr(bars)
            rv = compute_rv(bars)
            max_down, max_up = compute_max_moves(bars)

            print(f"    Underlying: {underlying_price}, ATR: {atr}, RV: {rv}")
            print(f"    Max 20d down: {max_down}, Max 20d up: {max_up}")
            print(f"    Bars: {len(bars)}")

        except Exception as e:
            print(f"    Bars error: {e}")
            continue

        # ── Pull option definitions via parent ──
        try:
            defn_store = client.timeseries.get_range(
                dataset=DATASET,
                symbols=symbol,
                stype_in="parent",
                schema="definition",
                start=(datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"),
                end=TODAY,
            )
            defns = records_to_list(defn_store)
            print(f"    Got {len(defns)} option definitions")

            if not defns:
                print(f"    No option definitions for {symbol}, skipping")
                continue

        except Exception as e:
            print(f"    Definition error: {e}")
            continue

        # ── Parse definitions ──
        instruments = {}  # instrument_id -> info
        for rec in defns:
            try:
                iid = getattr(rec, 'instrument_id', None)
                if iid is None or iid in instruments:
                    continue

                inst_class = str(getattr(rec, 'instrument_class', ''))
                if inst_class not in ('P', 'C'):
                    continue  # skip non-option definitions

                raw_sym = str(getattr(rec, 'raw_symbol', ''))
                strike = getattr(rec, 'pretty_strike_price', None)
                if strike is None:
                    strike_raw = getattr(rec, 'strike_price', None)
                    strike = safe_float(strike_raw) if strike_raw else None
                expiry = str(getattr(rec, 'pretty_expiration', ''))[:10]

                # Check expiry is 3-6 months out
                try:
                    exp_date = datetime.strptime(expiry, "%Y-%m-%d")
                    days_to_exp = (exp_date - datetime.now()).days
                    if days_to_exp < 60 or days_to_exp > 200:
                        continue
                except:
                    continue

                instruments[iid] = {
                    "instrument_id": iid,
                    "raw_symbol": raw_sym,
                    "strike": strike,
                    "type": "put" if inst_class == "P" else "call",
                    "expiration": expiry,
                    "days_to_exp": days_to_exp,
                }
            except:
                pass

        print(f"    Valid 3-6mo options: {len(instruments)}")
        if not instruments:
            continue

        # ── Pull settlement prices ──
        iid_list = [str(iid) for iid in list(instruments.keys())[:500]]  # limit batch

        try:
            stats_store = client.timeseries.get_range(
                dataset=DATASET,
                symbols=iid_list,
                stype_in="instrument_id",
                schema="statistics",
                start=(datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"),
                end=TODAY,
            )
            stats = records_to_list(stats_store)
            print(f"    Got {len(stats)} statistics records")

            # Extract settlement prices and OI
            for rec in stats:
                iid = getattr(rec, 'instrument_id', None)
                if iid not in instruments:
                    continue
                stat_type = str(getattr(rec, 'stat_type', ''))
                if 'SETTLEMENT' in stat_type:
                    price = getattr(rec, 'pretty_price', None)
                    if price is not None and not math.isnan(price):
                        instruments[iid]["settlement"] = price
                elif 'OPEN_INTEREST' in stat_type:
                    qty = getattr(rec, 'quantity', None)
                    if qty and qty < 9e18:
                        instruments[iid]["open_interest"] = qty
                elif 'CLEARED_VOLUME' in stat_type:
                    qty = getattr(rec, 'quantity', None)
                    if qty and qty < 9e18:
                        instruments[iid]["volume"] = qty

        except Exception as e:
            print(f"    Stats error: {e}")
            continue

        # ── Build chain_settlements for scoring context ──
        chain_settlements = []
        for iid, info in instruments.items():
            if "settlement" in info and info["settlement"] and info["settlement"] > 0:
                chain_settlements.append({
                    "strike": info["strike"],
                    "type": info["type"],
                    "settlement": info["settlement"],
                })

        print(f"    Options with settlements: {len(chain_settlements)}")

        # ── Score each option ──
        for iid, info in instruments.items():
            if "settlement" not in info or info["settlement"] is None or info["settlement"] <= 0:
                continue

            # Liquidity filter: at least some OI or volume
            oi = info.get("open_interest", 0) or 0
            vol = info.get("volume", 0) or 0
            if oi < 10 and vol < 5:
                continue  # too illiquid

            scores = score_option(
                opt=info,
                underlying_price=underlying_price,
                atr=atr,
                rv=rv,
                max_down_20d=max_down,
                max_up_20d=max_up,
                chain_settlements=chain_settlements,
                strike_div=strike_div,
            )

            if scores is None:
                continue

            strike_price = info["strike"] / strike_div if strike_div != 1 else info["strike"]

            results.append({
                "product": root,
                "product_name": product["name"],
                "symbol": info["raw_symbol"],
                "underlying_symbol": symbol,
                "type": info["type"],
                "strike": info["strike"],
                "strike_price": strike_price,
                "expiration": info["expiration"],
                "days_to_exp": info.get("days_to_exp", 0),
                "settlement": info["settlement"],
                "open_interest": oi,
                "volume": vol,
                "underlying_price": underlying_price,
                "atr": round(atr, 6) if atr else None,
                "rv_annual": round(rv, 6) if rv else None,
                **scores,
            })

    return results


def main():
    client = db.Historical(key=DATABENTO_KEY)

    all_results = []
    errors = []

    print("=" * 70)
    print("CME GLOBEX CHEAP OPTIONS SCANNER")
    print(f"Date: {TODAY}")
    print(f"Products: {len(PRODUCTS)}")
    print("=" * 70)

    for product in PRODUCTS:
        print(f"\n{'─' * 60}")
        print(f"Product: {product['root']} — {product['name']}")
        print(f"{'─' * 60}")

        try:
            results = scan_product(client, product)
            all_results.extend(results)
            print(f"  → Found {len(results)} scored options")
        except Exception as e:
            print(f"  → ERROR: {e}")
            errors.append({"product": product["root"], "error": str(e)})

    # Sort by composite score descending
    all_results.sort(key=lambda x: x["composite"], reverse=True)

    # ── Save full results ──
    output = {
        "scan_date": TODAY,
        "total_options_scored": len(all_results),
        "products_scanned": len(PRODUCTS),
        "errors": errors,
        "top_50": all_results[:50],
        "all_results": all_results,
    }

    outfile = "globex_scan_results.json"
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2, default=str)

    # ── Print summary ──
    print("\n" + "=" * 70)
    print("SCAN COMPLETE")
    print("=" * 70)
    print(f"Total options scored: {len(all_results)}")
    print(f"Errors: {len(errors)}")

    if all_results:
        print(f"\nTOP 25 CHEAPEST OPTIONS:")
        print(f"{'Symbol':<22} {'Type':<5} {'Strike':>10} {'Settle':>8} {'ATRs':>6} {'Comp':>6} {'EQ':>4} {'HM':>4} {'IV':>4} {'WL':>4} {'AC':>4} {'OI':>10} {'3xYield':>8}")
        print("─" * 115)
        for r in all_results[:25]:
            print(f"{r['symbol']:<22} {r['type']:<5} {r['strike_price']:>10.2f} {r['settlement']:>8.2f} "
                  f"{r['atrs_otm'] or 0:>6.1f} {r['composite']:>6.1f} "
                  f"{r['equidist']:>4} {r['historical']:>4} {r['iv_rv']:>4} {r['wing_loading']:>4} {r['absolute']:>4} "
                  f"{r['open_interest']:>10} {r['yield_3x']:>8.1f}")

    print(f"\nFull results saved to {outfile}")


if __name__ == "__main__":
    main()
