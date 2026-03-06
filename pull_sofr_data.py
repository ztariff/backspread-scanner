"""
Pull SR3M26 full option chain + futures data from Databento.
Run: pip3 install databento && python3 pull_sofr_data.py

CONFIRMED: Raw symbol format is "SR3M6 P9631" (space separated).
Underlying = "SR3M6". instrument_id for underlying = 254277.
Strike format: 9631 = 96.3125 (multiply by 0.01, min_price_increment = 0.25 ticks)

Strategy:
  1. Pull instrument definitions via parent to get ALL option symbols
  2. Pull mbp-1 quotes for each to get bid/ask/settlement
"""

import json
import sys

try:
    import databento as db
except ImportError:
    print("Install databento first: pip3 install databento")
    sys.exit(1)

DATABENTO_KEY = "db-qsqvF3QpT7mr6M75DyQC5N33NcTV5"
TARGET_DATE = "2026-02-27"
DATASET = "GLBX.MDP3"

output = {
    "target_date": TARGET_DATE,
    "underlying": {},
    "option_chain": [],
    "historical_bars": [],
}


def records_to_list(dbn_store):
    results = []
    try:
        for rec in dbn_store:
            results.append(rec)
    except Exception as e:
        print(f"  Iteration warning: {e}")
    return results


def safe_float(val):
    if val is None:
        return None
    v = float(val)
    if abs(v) > 1e6:
        return v / 1e9
    return v


def main():
    client = db.Historical(key=DATABENTO_KEY)

    # ──────────────────────────────────────────────────────────
    # 1. HISTORICAL BARS
    # ──────────────────────────────────────────────────────────
    print("=" * 60)
    print("1. HISTORICAL BARS (SR3M6)")
    print("=" * 60)
    try:
        bars_store = client.timeseries.get_range(
            dataset=DATASET,
            symbols="SR3M6",
            schema="ohlcv-1d",
            start="2025-06-01",
            end="2026-02-28",
        )
        bars = records_to_list(bars_store)
        print(f"  Got {len(bars)} daily bars")
        for bar in bars:
            try:
                output["historical_bars"].append({
                    "date": str(getattr(bar, 'ts_event', ''))[:10],
                    "open": safe_float(getattr(bar, 'open', None)),
                    "high": safe_float(getattr(bar, 'high', None)),
                    "low": safe_float(getattr(bar, 'low', None)),
                    "close": safe_float(getattr(bar, 'close', None)),
                    "volume": getattr(bar, 'volume', None),
                })
            except Exception as e:
                print(f"  Bar parse error: {e}")
    except Exception as e:
        print(f"  Historical bars error: {e}")

    # ──────────────────────────────────────────────────────────
    # 2. SETTLEMENT STATS
    # ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("2. SETTLEMENT STATS (SR3M6)")
    print("=" * 60)
    try:
        stats_store = client.timeseries.get_range(
            dataset=DATASET,
            symbols="SR3M6",
            schema="statistics",
            start=TARGET_DATE,
            end="2026-02-28",
        )
        stats = records_to_list(stats_store)
        print(f"  Got {len(stats)} stats records")
        for i, rec in enumerate(stats[:5]):
            entry = {}
            for attr in dir(rec):
                if attr.startswith('_'):
                    continue
                try:
                    val = getattr(rec, attr)
                    if not callable(val):
                        entry[attr] = str(val) if not isinstance(val, (int, float)) else val
                except:
                    pass
            output["underlying"][f"stat_{i}"] = entry
    except Exception as e:
        print(f"  Stats error: {e}")

    # ──────────────────────────────────────────────────────────
    # 3. FULL OPTION CHAIN — definitions via parent symbol
    # ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("3. OPTION CHAIN DEFINITIONS (parent=SR3M6)")
    print("=" * 60)

    # Build list of known option raw_symbols to query
    # CME SOFR options: SR3M6 {C|P}{strike}
    # Strike format: 9631 = 96.3125 (divide by 100)
    # Range: roughly 9500 to 9700 (95.00 to 97.00)
    # Tick size: 0.25 bps = strike increments of 25 (e.g., 9600, 9625, 9650, 9675, 9700)

    # Generate a set of option symbols to query
    option_symbols = []
    for strike_int in range(9500, 9725, 25):  # 95.00 to 97.00 in 0.25 increments
        option_symbols.append(f"SR3M6 P{strike_int}")
        option_symbols.append(f"SR3M6 C{strike_int}")
    # Also add some finer strikes near ATM (96.50 area)
    for strike_int in [9606, 9612, 9618, 9631, 9637, 9643, 9656, 9662, 9668]:
        option_symbols.append(f"SR3M6 P{strike_int}")
        option_symbols.append(f"SR3M6 C{strike_int}")

    # Remove dupes
    option_symbols = list(set(option_symbols))
    print(f"  Querying {len(option_symbols)} option symbols...")

    # Query definitions in batches to avoid too-large requests
    all_defns = []
    batch_size = 50
    for i in range(0, len(option_symbols), batch_size):
        batch = option_symbols[i:i+batch_size]
        print(f"  Batch {i//batch_size + 1}: {len(batch)} symbols...")
        try:
            defn_store = client.timeseries.get_range(
                dataset=DATASET,
                symbols=batch,
                stype_in="raw_symbol",
                schema="definition",
                start=TARGET_DATE,
                end="2026-02-28",
            )
            defns = records_to_list(defn_store)
            print(f"    Got {len(defns)} definitions")
            all_defns.extend(defns)
        except Exception as e:
            print(f"    Batch error: {e}")

    print(f"\n  Total definitions: {len(all_defns)}")

    # Now get instrument_ids to pull quotes
    instrument_ids = []
    defn_map = {}  # instrument_id -> definition info
    for rec in all_defns:
        try:
            iid = getattr(rec, 'instrument_id', None)
            raw_sym = str(getattr(rec, 'raw_symbol', ''))
            strike = getattr(rec, 'pretty_strike_price', None)
            if strike is None:
                strike = safe_float(getattr(rec, 'strike_price', None))
            inst_class = str(getattr(rec, 'instrument_class', ''))
            expiry = str(getattr(rec, 'pretty_expiration', ''))[:10]

            if iid and iid not in defn_map:
                instrument_ids.append(str(iid))
                defn_map[iid] = {
                    "instrument_id": iid,
                    "raw_symbol": raw_sym,
                    "strike": strike,
                    "type": "put" if inst_class == "P" else "call" if inst_class == "C" else inst_class,
                    "expiration": expiry,
                }
        except:
            pass

    print(f"  Unique instruments: {len(instrument_ids)}")

    # ──────────────────────────────────────────────────────────
    # 4. OPTION QUOTES — mbp-1 for each instrument
    # ──────────────────────────────────────────────────────────
    if instrument_ids:
        print("\n" + "=" * 60)
        print("4. OPTION QUOTES (mbp-1)")
        print("=" * 60)

        # Pull quotes for all instrument IDs
        try:
            quotes_store = client.timeseries.get_range(
                dataset=DATASET,
                symbols=instrument_ids,
                stype_in="instrument_id",
                schema="mbp-1",
                start=TARGET_DATE + "T14:00",
                end=TARGET_DATE + "T22:00",
            )
            quotes = records_to_list(quotes_store)
            print(f"  Got {len(quotes)} quote records")

            # Group quotes by instrument_id, take the latest
            latest_quotes = {}
            for rec in quotes:
                iid = getattr(rec, 'instrument_id', None)
                if iid:
                    latest_quotes[iid] = rec  # keeps overwriting → last = latest

            print(f"  Unique instruments with quotes: {len(latest_quotes)}")

            # Merge definitions with quotes
            for iid, defn_info in defn_map.items():
                entry = dict(defn_info)
                if iid in latest_quotes:
                    q = latest_quotes[iid]
                    bid = safe_float(getattr(q, 'bid_px_00', None))
                    ask = safe_float(getattr(q, 'ask_px_00', None))
                    entry["bid"] = bid
                    entry["ask"] = ask
                    entry["mid"] = round((bid + ask) / 2, 6) if bid and ask else None
                    entry["bid_sz"] = getattr(q, 'bid_sz_00', None)
                    entry["ask_sz"] = getattr(q, 'ask_sz_00', None)
                else:
                    entry["bid"] = None
                    entry["ask"] = None
                    entry["mid"] = None

                output["option_chain"].append(entry)

        except Exception as e:
            print(f"  Quotes error: {e}")
            # Fall back: save definitions without quotes
            for iid, defn_info in defn_map.items():
                output["option_chain"].append(defn_info)
    else:
        print("\n  No instrument IDs found, skipping quotes.")

    # Also try pulling statistics (settlement prices) for options
    if instrument_ids:
        print("\n" + "=" * 60)
        print("5. OPTION SETTLEMENT PRICES")
        print("=" * 60)
        try:
            opt_stats_store = client.timeseries.get_range(
                dataset=DATASET,
                symbols=instrument_ids[:100],  # limit
                stype_in="instrument_id",
                schema="statistics",
                start=TARGET_DATE,
                end="2026-02-28",
            )
            opt_stats = records_to_list(opt_stats_store)
            print(f"  Got {len(opt_stats)} option statistics records")

            # Find settlement prices
            settlements = {}
            for rec in opt_stats:
                iid = getattr(rec, 'instrument_id', None)
                stat_type = str(getattr(rec, 'stat_type', ''))
                if 'SETTLEMENT' in stat_type and iid:
                    settlements[iid] = safe_float(getattr(rec, 'price', None))

            print(f"  Settlement prices found: {len(settlements)}")

            # Add settlement prices to option chain entries
            for entry in output["option_chain"]:
                iid = entry.get("instrument_id")
                if iid in settlements:
                    entry["settlement"] = settlements[iid]

        except Exception as e:
            print(f"  Option stats error: {e}")

    # ──────────────────────────────────────────────────────────
    # Sort and save
    # ──────────────────────────────────────────────────────────
    output["option_chain"].sort(key=lambda x: (x.get("type", ""), x.get("strike", 0)))

    outfile = "sr3m26_data.json"
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Historical bars: {len(output['historical_bars'])}")
    print(f"  Option chain entries: {len(output['option_chain'])}")

    # Print a nice table of the chain
    puts = [e for e in output['option_chain'] if e.get('type') == 'put']
    calls = [e for e in output['option_chain'] if e.get('type') == 'call']
    print(f"  Puts: {len(puts)}, Calls: {len(calls)}")

    print("\n  Sample option chain (puts near 96.3125):")
    for e in puts:
        s = e.get('strike', 0)
        if s and 9600 <= s <= 9650:
            print(f"    {e.get('raw_symbol',''):20s}  strike={s:8.2f}  bid={e.get('bid','?'):>8}  ask={e.get('ask','?'):>8}  settle={e.get('settlement','?')}")

    print(f"\nSaved to {outfile}")


if __name__ == "__main__":
    main()
