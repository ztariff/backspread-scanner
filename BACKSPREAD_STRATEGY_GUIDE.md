# Diagonal Ratio Backspread: Convexity Harvesting Strategy Guide

## The Core Idea

Buy large quantities of cheap, far out-of-the-money options on a longer expiration. Sell fewer contracts of closer-to-the-money options on a shorter expiration to finance the purchase. The short leg expires, leaving you holding free (or near-free) convexity. If a tail event occurs before the long leg expires, the payoff is asymmetric — potentially hundreds or thousands of percent.

This is the strategy Nassim Taleb ran on Eurodollar calls leading up to Black Monday in 1987. The far OTM Eurodollar calls were priced as if a large rate move would never happen. He accumulated them cheaply, financed the position with shorter-dated premium, and held for months with small P&L fluctuations until the Fed's emergency rate cut produced a 150,000%+ return on the long calls.


## Structure

**Long Leg (convexity):**
- Far out-of-the-money options (calls OR puts — never mixed)
- Longer-dated expiration (weeks to months out)
- Large quantity — you're accumulating lottery tickets
- Must be cheap in absolute dollar terms and relative to the opposite wing

**Short Leg (financing):**
- At-the-money or slightly OTM options in the SAME direction (calls against calls, puts against puts)
- Shorter-dated expiration (days to a couple weeks)
- Fewer contracts than the long leg
- Sized so that the premium received roughly covers the cost of the long leg

**Example (SPX fear environment, calls cheap):**

SPX at 5800. Puts are expensive due to fear. Calls are neglected.

- Buy 50x SPX $6100 calls expiring in 30 days @ $0.80 each = $4,000 debit
- Sell 2x SPX $5850 calls expiring in 5 days @ $20.00 each = $4,000 credit
- Net cost: ~$0 (premium neutral)
- Ratio: 25:1

After 5 days, the short calls expire (worthless if SPX hasn't rallied through $5850). You now own 50 free SPX $6100 calls with 25 days left. If SPX gaps up 5% to $6090, those calls are now worth $5-15+ each = $25,000-$75,000 from a $0 starting position.


## When to Enter: Finding "Cheap"

The entire strategy depends on identifying options that are genuinely underpriced. The scanner measures cheapness across five dimensions:

### 1. Equidistant Comparison (30% of cheapness score)

The single most powerful signal. Compare the price of your target option to the equidistant option on the opposite side of the chain. If SPX is at 5800: compare the $5500 put to the $6100 call. Both are $300 OTM. If the $5500 put costs $45 and the $6100 call costs $0.80, the call is 56x cheaper. That's extreme asymmetry — the market is saying one tail is possible and the other isn't.

This measure captures fear regimes (puts expensive, calls cheap), euphoria regimes (calls expensive, puts cheap), and sector-specific dislocations.

### 2. Price vs. Historical Moves (25% of cheapness score)

Has the underlying ever moved far enough to put this option deep in the money? If SPX has made a 10% move in a 20-day window within the past year, and a 10% OTM option is priced at $0.10, the option is dramatically underpricing a move that has actually occurred.

The scanner calculates: if the largest historical move repeated, what would this option be worth at expiration? If a $0.10 option would be worth $50, that's a 500x yield ratio. The option is priced as if the underlying can never move that far, despite evidence that it has.

### 3. IV vs. Realized Volatility (20% of cheapness score)

If the option's implied volatility is below the underlying's realized volatility, the market is underpricing actual movement. An IV/RV ratio below 1.0 means the option is cheaper than what recent history would justify. Below 0.7 is a strong signal.

### 4. Absolute Cheapness (10% of cheapness score)

Simple: is the option cheap in dollar terms? Penny options ($0.05-$0.25) let you accumulate massive quantities. A $0.10 option that goes to $5.00 is a 50x return. The lower the absolute price, the more leverage you get per dollar deployed.

### 5. Wing Loading (15% of cheapness score)

Is the entire wing systematically cheap? If the average IV of all OTM calls is 14% while the average IV of all OTM puts is 35%, the call wing is structurally underpriced. This catches regime-level mispricing rather than individual contract anomalies.


## The Financing Mechanism

The short leg is not a trade in itself — it's a funding mechanism. You sell premium that you expect to decay quickly, and use the proceeds to buy the cheap convexity.

**Key principles:**

The short leg should be same-direction only. Long calls are financed by short calls. Long puts are financed by short puts. Never cross (long calls against short puts), because that creates undefined risk in the opposite direction and defeats the purpose of the asymmetric structure.

The short leg should expire well before the long leg. Ideally within 1-14 days. The theta decay on a 3-5 DTE option is brutal — that's your friend when you're short. Once the short leg expires, the long leg is free.

Premium neutrality is the target. Size the short leg so that the credit received roughly equals the cost of the long leg. Slight net debit is acceptable. Net credit is even better — you get paid to own convexity.

The short leg should be ATM or slightly OTM. You need enough premium to finance the long leg. Deep OTM shorts don't generate enough credit. Delta range of 0.25-0.60 is the sweet spot.


## Risk Profile

**What you can lose:**
If the short leg goes in-the-money before expiring, you have a loss on those contracts. This is bounded because you sold fewer contracts than you bought. Worst case on the short leg: the underlying moves through your short strike before that expiration. Your loss is (move x short qty x 100) minus the credit received. After the short leg expires, your only risk on the remaining long position is the net premium paid (which should be near zero).

**What you can make:**
If the underlying makes a large move in your direction before the long leg expires, the payoff is potentially enormous. A 10-20% move on a $0.10 option can produce 100x-1000x+ returns. Even moderate IV expansion on the long leg (before a move happens) creates mark-to-market gains.

**The dead zone:**
Small moves in your direction won't help. If you own $6100 calls and SPX goes from $5800 to $5900, your calls are still far OTM. You need the big move. Time decay on the long leg after the short leg expires is a factor — you're naked long far OTM options that lose theta daily. But since they cost you ~nothing, the theta bleed is from house money.


## When NOT to Enter

**Skew is flat.** If calls and puts at equidistant OTM are similarly priced, neither wing is cheap. The edge isn't there.

**IV is extremely low everywhere.** If the entire vol surface is suppressed (VIX < 12), far OTM options may technically be cheap but so is everything else. There's less room for IV expansion to amplify your position.

**No historical precedent for a large move.** If the underlying has never moved more than 3% in a day and you're buying 20% OTM options, the option may be correctly priced. Check the max move data.

**You can't finance it cheaply enough.** If the short-dated ATM options don't generate enough premium to cover the long leg, the trade carries too much net debit. It stops being a free lottery ticket and starts being a bet.


## Same-Expiry (0DTE) Backspreads

The scanner also supports same-expiry ratio backspreads. Instead of different expirations, both legs share the same expiry — including 0DTE. The structure is the same: buy many far-OTM options, sell fewer ATM-ish options to finance them, all on the same expiration.

This works when intraday or overnight cheapness exists (one wing is dramatically cheaper than the other). The trade doesn't rely on time decay of the short leg — instead, it relies purely on the asymmetry of the payoff. The short leg provides financing, and the long leg provides convexity, but both expire simultaneously.

Same-expiry backspreads are most useful in high-volatility environments where you expect a large move within the day. The scanner automatically considers same-expiry structures alongside diagonals and ranks them together.


## Scanner Usage

The scanner automatically detects which side of the chain is cheap — no need to specify direction. It scans both calls and puts, looking for skew-driven mispricings on either wing.

```bash
# Scan default universe (SPY, QQQ, TSLA, AAPL, etc.)
python scanner.py --show-cheapness

# Scan specific tickers
python scanner.py --tickers SPY,QQQ,AAPL,TSLA

# Scan major ETFs with cheapness report
python scanner.py --universe etfs --show-cheapness

# Look for very cheap options only
python scanner.py --tickers SPY --max-price 1.00 --min-otm 0.10

# Detailed view with skew analysis
python scanner.py --tickers SPY --format detailed --show-skew --show-cheapness -v

# Export results
python scanner.py --universe etfs --output results.csv

# Broader OTM range for high-conviction environments
python scanner.py --tickers SPY --min-otm 0.03 --max-otm 0.50 --max-price 10.00
```

**Key CLI arguments:**
- `--tickers` / `--universe` — ticker selection (optional; defaults to curated list)
- `--max-price` — maximum price for a "cheap" option (default $5)
- `--min-otm` / `--max-otm` — how far OTM the long leg should be
- `--min-cheapness` — minimum cheapness score to show (0-100, default 20)
- `--show-cheapness` — display the cheapness report before trade construction
- `--show-skew` — show skew analysis for each chain
- `--long-expiry` / `--short-expiry` — pin specific expiration dates


## Setup

1. Get a Polygon.io API key (options snapshots require a paid tier for real-time data; the contracts fallback works on free but is slower).
2. Copy `.env.example` to `.env` and set your `POLYGON_API_KEY`.
3. Install dependencies: `pip install -r requirements.txt`
4. Run: `python scanner.py --show-cheapness -v`
