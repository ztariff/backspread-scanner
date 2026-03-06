import { useState, useMemo, useCallback, useEffect } from "react";
import {
  BarChart, Bar, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, Legend
} from "recharts";
import {
  Upload, X, ChevronUp, ChevronDown, Filter, TrendingUp,
  DollarSign, Target, Zap, RotateCcw, FileJson
} from "lucide-react";

// ══════════════════════════════════════════════════════════════
// Demo Data — fear-regime: calls are cheap, puts are expensive
// ══════════════════════════════════════════════════════════════
const DEMO_DATA = [
  { ticker: "SPY", direction: "call", long_strike: 620, long_exp: "2026-04-17", long_price: 0.45, long_qty: 12, short_strike: 585, short_exp: "2026-03-06", short_price: 5.40, short_qty: 1, ratio: "12:1", net_premium: -0.00, premium_neutral_pct: 0.0, cheapness: 82.5, equidist_ratio: 4.8, iv_rv: 0.72, hist_move_yield: 18, tail_payoff: 4200, net_delta: 12.4, net_vega: 35.2, net_theta: -1.85, score: 88.2 },
  { ticker: "SPY", direction: "call", long_strike: 630, long_exp: "2026-04-17", long_price: 0.18, long_qty: 30, short_strike: 585, short_exp: "2026-03-06", short_price: 5.40, short_qty: 1, ratio: "30:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 91.3, equidist_ratio: 6.2, iv_rv: 0.65, hist_move_yield: 32, tail_payoff: 6800, net_delta: 8.1, net_vega: 42.0, net_theta: -2.10, score: 92.1 },
  { ticker: "SPY", direction: "put", long_strike: 540, long_exp: "2026-04-17", long_price: 3.20, long_qty: 3, short_strike: 575, short_exp: "2026-03-06", short_price: 9.60, short_qty: 1, ratio: "3:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 38.4, equidist_ratio: 1.4, iv_rv: 1.15, hist_move_yield: 5, tail_payoff: 1200, net_delta: -18.5, net_vega: 22.0, net_theta: -0.95, score: 52.3 },
  { ticker: "SPY", direction: "put", long_strike: 530, long_exp: "2026-04-17", long_price: 2.40, long_qty: 4, short_strike: 575, short_exp: "2026-03-06", short_price: 9.60, short_qty: 1, ratio: "4:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 42.1, equidist_ratio: 1.6, iv_rv: 1.10, hist_move_yield: 7, tail_payoff: 1800, net_delta: -22.1, net_vega: 28.0, net_theta: -1.20, score: 55.8 },
  { ticker: "QQQ", direction: "call", long_strike: 540, long_exp: "2026-04-17", long_price: 0.52, long_qty: 10, short_strike: 505, short_exp: "2026-03-06", short_price: 5.20, short_qty: 1, ratio: "10:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 78.9, equidist_ratio: 4.2, iv_rv: 0.78, hist_move_yield: 15, tail_payoff: 3500, net_delta: 10.8, net_vega: 30.5, net_theta: -1.65, score: 84.7 },
  { ticker: "QQQ", direction: "call", long_strike: 550, long_exp: "2026-05-15", long_price: 0.85, long_qty: 6, short_strike: 505, short_exp: "2026-03-06", short_price: 5.20, short_qty: 1, ratio: "6:1", net_premium: -10.00, premium_neutral_pct: 2.0, cheapness: 71.2, equidist_ratio: 3.5, iv_rv: 0.82, hist_move_yield: 12, tail_payoff: 2800, net_delta: 14.2, net_vega: 38.0, net_theta: -1.45, score: 79.5 },
  { ticker: "QQQ", direction: "put", long_strike: 460, long_exp: "2026-04-17", long_price: 2.80, long_qty: 4, short_strike: 495, short_exp: "2026-03-06", short_price: 11.20, short_qty: 1, ratio: "4:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 35.6, equidist_ratio: 1.3, iv_rv: 1.20, hist_move_yield: 4, tail_payoff: 980, net_delta: -20.4, net_vega: 18.0, net_theta: -0.88, score: 48.2 },
  { ticker: "TSLA", direction: "call", long_strike: 450, long_exp: "2026-04-17", long_price: 1.20, long_qty: 8, short_strike: 390, short_exp: "2026-03-06", short_price: 9.60, short_qty: 1, ratio: "8:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 74.8, equidist_ratio: 3.8, iv_rv: 0.68, hist_move_yield: 22, tail_payoff: 5200, net_delta: 15.6, net_vega: 52.0, net_theta: -2.80, score: 82.4 },
  { ticker: "TSLA", direction: "call", long_strike: 480, long_exp: "2026-05-15", long_price: 0.35, long_qty: 20, short_strike: 390, short_exp: "2026-03-06", short_price: 7.00, short_qty: 1, ratio: "20:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 88.5, equidist_ratio: 5.5, iv_rv: 0.58, hist_move_yield: 45, tail_payoff: 8500, net_delta: 6.2, net_vega: 48.0, net_theta: -2.40, score: 90.8 },
  { ticker: "TSLA", direction: "put", long_strike: 280, long_exp: "2026-04-17", long_price: 2.10, long_qty: 5, short_strike: 370, short_exp: "2026-03-06", short_price: 10.50, short_qty: 1, ratio: "5:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 45.2, equidist_ratio: 1.8, iv_rv: 1.05, hist_move_yield: 8, tail_payoff: 2100, net_delta: -25.3, net_vega: 32.0, net_theta: -1.55, score: 58.9 },
  { ticker: "AAPL", direction: "call", long_strike: 270, long_exp: "2026-04-17", long_price: 0.65, long_qty: 8, short_strike: 248, short_exp: "2026-03-06", short_price: 5.20, short_qty: 1, ratio: "8:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 72.1, equidist_ratio: 3.6, iv_rv: 0.80, hist_move_yield: 14, tail_payoff: 2900, net_delta: 11.2, net_vega: 28.0, net_theta: -1.35, score: 78.4 },
  { ticker: "AAPL", direction: "put", long_strike: 210, long_exp: "2026-04-17", long_price: 1.80, long_qty: 3, short_strike: 240, short_exp: "2026-03-06", short_price: 5.40, short_qty: 1, ratio: "3:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 40.8, equidist_ratio: 1.5, iv_rv: 1.12, hist_move_yield: 6, tail_payoff: 1100, net_delta: -15.8, net_vega: 20.0, net_theta: -0.92, score: 53.1 },
  { ticker: "NVDA", direction: "call", long_strike: 170, long_exp: "2026-04-17", long_price: 0.90, long_qty: 7, short_strike: 142, short_exp: "2026-03-06", short_price: 6.30, short_qty: 1, ratio: "7:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 76.3, equidist_ratio: 4.1, iv_rv: 0.74, hist_move_yield: 20, tail_payoff: 4100, net_delta: 13.5, net_vega: 45.0, net_theta: -2.20, score: 83.6 },
  { ticker: "NVDA", direction: "call", long_strike: 180, long_exp: "2026-05-15", long_price: 0.40, long_qty: 15, short_strike: 142, short_exp: "2026-03-06", short_price: 6.00, short_qty: 1, ratio: "15:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 85.7, equidist_ratio: 5.0, iv_rv: 0.62, hist_move_yield: 35, tail_payoff: 7200, net_delta: 7.8, net_vega: 50.0, net_theta: -2.50, score: 89.3 },
  { ticker: "GLD", direction: "call", long_strike: 300, long_exp: "2026-05-15", long_price: 0.55, long_qty: 9, short_strike: 275, short_exp: "2026-03-06", short_price: 4.95, short_qty: 1, ratio: "9:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 68.4, equidist_ratio: 3.2, iv_rv: 0.85, hist_move_yield: 11, tail_payoff: 2200, net_delta: 9.5, net_vega: 22.0, net_theta: -1.10, score: 74.2 },
  { ticker: "GLD", direction: "put", long_strike: 240, long_exp: "2026-04-17", long_price: 1.60, long_qty: 3, short_strike: 268, short_exp: "2026-03-06", short_price: 4.80, short_qty: 1, ratio: "3:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 44.5, equidist_ratio: 1.7, iv_rv: 1.08, hist_move_yield: 6, tail_payoff: 950, net_delta: -12.8, net_vega: 16.0, net_theta: -0.78, score: 56.4 },
  { ticker: "AMD", direction: "call", long_strike: 155, long_exp: "2026-04-17", long_price: 0.72, long_qty: 7, short_strike: 128, short_exp: "2026-03-06", short_price: 5.04, short_qty: 1, ratio: "7:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 70.5, equidist_ratio: 3.4, iv_rv: 0.76, hist_move_yield: 16, tail_payoff: 3400, net_delta: 12.0, net_vega: 38.0, net_theta: -1.90, score: 77.8 },
  { ticker: "MU", direction: "call", long_strike: 120, long_exp: "2026-05-15", long_price: 0.48, long_qty: 10, short_strike: 98, short_exp: "2026-03-06", short_price: 4.80, short_qty: 1, ratio: "10:1", net_premium: 0.00, premium_neutral_pct: 0.0, cheapness: 73.8, equidist_ratio: 3.9, iv_rv: 0.70, hist_move_yield: 19, tail_payoff: 3800, net_delta: 9.8, net_vega: 34.0, net_theta: -1.70, score: 80.1 },
];

// ══════════════════════════════════════════════════════════════
// Helper functions
// ══════════════════════════════════════════════════════════════
const fmt$ = (v) => v == null ? "—" : (v < 0 ? `-$${Math.abs(v).toLocaleString()}` : `$${v.toLocaleString()}`);
const fmtPct = (v) => v == null ? "—" : `${v.toFixed(1)}%`;
const fmtNum = (v, d = 1) => v == null ? "—" : v.toFixed(d);

const CALL_COLOR = "#10b981";
const PUT_COLOR = "#ef4444";
const ACCENT = "#3b82f6";
const CHART_COLORS = { call: CALL_COLOR, put: PUT_COLOR };

// ══════════════════════════════════════════════════════════════
// Main Dashboard Component
// ══════════════════════════════════════════════════════════════
export default function BackspreadDashboard() {
  const [rawData, setRawData] = useState(DEMO_DATA);
  const [sortKey, setSortKey] = useState("score");
  const [sortDir, setSortDir] = useState("desc");
  const [selectedTrade, setSelectedTrade] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    tickers: [],
    direction: "both",
    minCheapness: 0,
    minScore: 0,
  });

  // Available tickers from data
  const availableTickers = useMemo(() =>
    [...new Set(rawData.map(d => d.ticker))].sort(),
    [rawData]
  );

  // Filter + sort
  const filteredData = useMemo(() => {
    let data = rawData.filter(d => {
      if (filters.tickers.length > 0 && !filters.tickers.includes(d.ticker)) return false;
      if (filters.direction !== "both" && d.direction !== filters.direction) return false;
      if (d.cheapness < filters.minCheapness) return false;
      if (d.score < filters.minScore) return false;
      return true;
    });
    data.sort((a, b) => {
      const av = a[sortKey] ?? 0;
      const bv = b[sortKey] ?? 0;
      if (typeof av === "string") return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      return sortDir === "asc" ? av - bv : bv - av;
    });
    return data;
  }, [rawData, filters, sortKey, sortDir]);

  // Summary stats
  const stats = useMemo(() => {
    if (filteredData.length === 0) return { count: 0, avgCheap: 0, bestScore: 0, bestTail: 0 };
    return {
      count: filteredData.length,
      avgCheap: filteredData.reduce((s, d) => s + d.cheapness, 0) / filteredData.length,
      bestScore: Math.max(...filteredData.map(d => d.score)),
      bestTail: Math.max(...filteredData.map(d => d.tail_payoff || 0)),
    };
  }, [filteredData]);

  // Chart data
  const histogramData = useMemo(() => {
    const bins = Array.from({ length: 10 }, (_, i) => ({
      range: `${i * 10}-${(i + 1) * 10}`,
      count: 0, calls: 0, puts: 0,
    }));
    filteredData.forEach(d => {
      const idx = Math.min(Math.floor(d.cheapness / 10), 9);
      bins[idx].count++;
      if (d.direction === "call") bins[idx].calls++;
      else bins[idx].puts++;
    });
    return bins;
  }, [filteredData]);

  const scatterData = useMemo(() =>
    filteredData.map(d => ({
      cheapness: d.cheapness,
      score: d.score,
      direction: d.direction,
      ticker: d.ticker,
      tail: d.tail_payoff || 0,
    })),
    [filteredData]
  );

  // Handlers
  const handleSort = useCallback((key) => {
    setSortKey(prev => {
      if (prev === key) {
        setSortDir(d => d === "asc" ? "desc" : "asc");
        return key;
      }
      setSortDir("desc");
      return key;
    });
  }, []);

  const toggleTicker = useCallback((t) => {
    setFilters(f => ({
      ...f,
      tickers: f.tickers.includes(t)
        ? f.tickers.filter(x => x !== t)
        : [...f.tickers, t],
    }));
  }, []);

  const handleFile = useCallback((file) => {
    setError(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const json = JSON.parse(e.target.result);
        const arr = Array.isArray(json) ? json : [json];
        if (arr.length === 0 || !arr[0].ticker) {
          setError("Invalid JSON: expected array of trade objects with 'ticker' field");
          return;
        }
        setRawData(arr);
        setFilters({ tickers: [], direction: "both", minCheapness: 0, minScore: 0 });
      } catch {
        setError("Failed to parse JSON file");
      }
    };
    reader.readAsText(file);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer?.files?.[0];
    if (file) handleFile(file);
  }, [handleFile]);

  // ESC to close modal
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") setSelectedTrade(null); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const SortIcon = ({ col }) => {
    if (sortKey !== col) return <ChevronDown className="w-3 h-3 opacity-30 inline ml-1" />;
    return sortDir === "asc"
      ? <ChevronUp className="w-3 h-3 inline ml-1 text-blue-400" />
      : <ChevronDown className="w-3 h-3 inline ml-1 text-blue-400" />;
  };

  // ════════════════════════════════════════════════════════════
  // Render
  // ════════════════════════════════════════════════════════════
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-4 font-sans">
      {/* ── Header ────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Zap className="w-6 h-6 text-yellow-400" />
            Ratio Backspread Scanner
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Taleb-style convexity harvesting — cheap wings, premium-neutral financing
          </p>
        </div>

        <div className="flex items-center gap-3">
          <label
            className={`flex items-center gap-2 px-4 py-2 rounded-lg border-2 border-dashed cursor-pointer transition-colors
              ${dragOver ? "border-blue-400 bg-blue-500/10" : "border-slate-600 hover:border-slate-400"}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
          >
            <Upload className="w-4 h-4" />
            <span className="text-sm">Load JSON</span>
            <input
              type="file"
              accept=".json"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
            />
          </label>
          <button
            onClick={() => {
              setRawData(DEMO_DATA);
              setFilters({ tickers: [], direction: "both", minCheapness: 0, minScore: 0 });
              setError(null);
            }}
            className="flex items-center gap-1 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-sm transition-colors"
          >
            <RotateCcw className="w-3 h-3" /> Demo
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm flex items-center gap-2">
          <X className="w-4 h-4 flex-shrink-0" />
          {error}
          <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-200">dismiss</button>
        </div>
      )}

      {/* ── Summary Cards ────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {[
          { label: "Opportunities", value: stats.count, icon: <Target className="w-5 h-5" />, color: "text-blue-400" },
          { label: "Avg Cheapness", value: fmtNum(stats.avgCheap), icon: <TrendingUp className="w-5 h-5" />, color: "text-emerald-400" },
          { label: "Best Score", value: fmtNum(stats.bestScore), icon: <Zap className="w-5 h-5" />, color: "text-yellow-400" },
          { label: "Best Tail Payoff", value: fmt$(stats.bestTail), icon: <DollarSign className="w-5 h-5" />, color: "text-purple-400" },
        ].map((card) => (
          <div key={card.label} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <div className="flex items-center gap-2 text-slate-400 text-xs uppercase tracking-wider mb-2">
              <span className={card.color}>{card.icon}</span>
              {card.label}
            </div>
            <div className="text-2xl font-bold">{card.value}</div>
          </div>
        ))}
      </div>

      {/* ── Filter Bar ───────────────────────────────── */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-6">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-1 text-slate-400 text-sm">
            <Filter className="w-4 h-4" /> Filters
          </div>

          {/* Ticker chips */}
          <div className="flex flex-wrap gap-1">
            {availableTickers.map(t => (
              <button
                key={t}
                onClick={() => toggleTicker(t)}
                className={`px-2 py-0.5 rounded text-xs font-medium transition-colors
                  ${filters.tickers.includes(t) || filters.tickers.length === 0
                    ? "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                    : "bg-slate-800 text-slate-500 border border-slate-700"}`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Direction toggle */}
          <div className="flex rounded-lg overflow-hidden border border-slate-700">
            {["both", "call", "put"].map(d => (
              <button
                key={d}
                onClick={() => setFilters(f => ({ ...f, direction: d }))}
                className={`px-3 py-1 text-xs font-medium transition-colors
                  ${filters.direction === d
                    ? d === "call" ? "bg-emerald-500/20 text-emerald-300"
                      : d === "put" ? "bg-red-500/20 text-red-300"
                      : "bg-blue-500/20 text-blue-300"
                    : "bg-slate-800 text-slate-500"}`}
              >
                {d === "both" ? "All" : d.charAt(0).toUpperCase() + d.slice(1) + "s"}
              </button>
            ))}
          </div>

          {/* Sliders */}
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span>Cheapness &ge; {filters.minCheapness}</span>
            <input
              type="range" min="0" max="100" step="5"
              value={filters.minCheapness}
              onChange={(e) => setFilters(f => ({ ...f, minCheapness: +e.target.value }))}
              className="w-24 accent-blue-500"
            />
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span>Score &ge; {filters.minScore}</span>
            <input
              type="range" min="0" max="100" step="5"
              value={filters.minScore}
              onChange={(e) => setFilters(f => ({ ...f, minScore: +e.target.value }))}
              className="w-24 accent-blue-500"
            />
          </div>

          {(filters.tickers.length > 0 || filters.direction !== "both" || filters.minCheapness > 0 || filters.minScore > 0) && (
            <button
              onClick={() => setFilters({ tickers: [], direction: "both", minCheapness: 0, minScore: 0 })}
              className="px-2 py-1 rounded text-xs text-slate-400 hover:text-slate-200 bg-slate-800 hover:bg-slate-700 transition-colors"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* ── Main Table ───────────────────────────────── */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden mb-6">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 text-xs uppercase tracking-wider">
                {[
                  { key: "ticker", label: "Ticker", align: "left" },
                  { key: "direction", label: "Dir", align: "center" },
                  { key: "long_strike", label: "Long Leg", align: "left" },
                  { key: "short_strike", label: "Short Leg", align: "left" },
                  { key: "ratio", label: "Ratio", align: "center" },
                  { key: "net_premium", label: "Net $", align: "right" },
                  { key: "cheapness", label: "Cheap", align: "right" },
                  { key: "tail_payoff", label: "Tail $", align: "right" },
                  { key: "score", label: "Score", align: "right" },
                ].map(col => (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    className={`px-3 py-3 cursor-pointer hover:text-slate-200 transition-colors select-none
                      ${col.align === "right" ? "text-right" : col.align === "center" ? "text-center" : "text-left"}`}
                  >
                    {col.label}<SortIcon col={col.key} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredData.length === 0 ? (
                <tr><td colSpan={9} className="text-center py-12 text-slate-500">
                  No opportunities match your filters
                </td></tr>
              ) : filteredData.map((d, i) => (
                <tr
                  key={i}
                  onClick={() => setSelectedTrade(d)}
                  className="border-b border-slate-800/50 hover:bg-slate-800/50 cursor-pointer transition-colors"
                >
                  <td className="px-3 py-2.5 font-medium">{d.ticker}</td>
                  <td className="px-3 py-2.5 text-center">
                    <span className={`px-1.5 py-0.5 rounded text-xs font-medium
                      ${d.direction === "call" ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"}`}>
                      {d.direction === "call" ? "C" : "P"}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-slate-300">
                    <span className="font-medium">${d.long_strike}</span>
                    <span className="text-slate-500 text-xs ml-1">{d.long_exp.slice(5)} @${d.long_price} x{d.long_qty}</span>
                  </td>
                  <td className="px-3 py-2.5 text-slate-300">
                    <span className="font-medium">${d.short_strike}</span>
                    <span className="text-slate-500 text-xs ml-1">{d.short_exp.slice(5)} @${d.short_price} x{d.short_qty}</span>
                  </td>
                  <td className="px-3 py-2.5 text-center text-slate-300">{d.ratio}</td>
                  <td className={`px-3 py-2.5 text-right ${d.net_premium < 0 ? "text-emerald-400" : d.net_premium > 0 ? "text-red-400" : "text-slate-400"}`}>
                    {fmt$(d.net_premium)}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <span className="font-medium">{fmtNum(d.cheapness)}</span>
                    <div className="w-full bg-slate-800 rounded-full h-1 mt-1">
                      <div
                        className="h-1 rounded-full bg-emerald-500"
                        style={{ width: `${d.cheapness}%` }}
                      />
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right text-slate-300">{fmt$(d.tail_payoff)}</td>
                  <td className="px-3 py-2.5 text-right">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-bold
                      ${d.score >= 85 ? "bg-yellow-500/20 text-yellow-300"
                        : d.score >= 70 ? "bg-emerald-500/20 text-emerald-300"
                        : d.score >= 50 ? "bg-blue-500/20 text-blue-300"
                        : "bg-slate-700 text-slate-400"}`}>
                      {fmtNum(d.score)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Charts ───────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        {/* Cheapness distribution */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <h3 className="text-sm font-medium text-slate-400 mb-3">Cheapness Distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={histogramData} barGap={1}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="range" tick={{ fill: "#94a3b8", fontSize: 11 }} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} allowDecimals={false} />
              <Tooltip
                contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                labelStyle={{ color: "#e2e8f0" }}
              />
              <Bar dataKey="calls" stackId="a" fill={CALL_COLOR} name="Calls" radius={[0, 0, 0, 0]} />
              <Bar dataKey="puts" stackId="a" fill={PUT_COLOR} name="Puts" radius={[4, 4, 0, 0]} />
              <Legend wrapperStyle={{ fontSize: 11, color: "#94a3b8" }} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Score vs Cheapness scatter */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <h3 className="text-sm font-medium text-slate-400 mb-3">Score vs Cheapness</h3>
          <ResponsiveContainer width="100%" height={220}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="cheapness" name="Cheapness" tick={{ fill: "#94a3b8", fontSize: 11 }}
                domain={[0, 100]} label={{ value: "Cheapness", position: "bottom", fill: "#64748b", fontSize: 11, offset: -2 }} />
              <YAxis dataKey="score" name="Score" tick={{ fill: "#94a3b8", fontSize: 11 }}
                domain={[0, 100]} label={{ value: "Score", angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 11 }} />
              <Tooltip
                contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                formatter={(val, name) => [fmtNum(val), name]}
                labelFormatter={() => ""}
                cursor={{ strokeDasharray: "3 3", stroke: "#475569" }}
                content={({ payload }) => {
                  if (!payload?.length) return null;
                  const d = payload[0].payload;
                  return (
                    <div className="bg-slate-800 border border-slate-700 rounded-lg p-2 text-xs">
                      <div className="font-bold text-slate-100">{d.ticker}
                        <span className={d.direction === "call" ? "text-emerald-400" : "text-red-400"}> {d.direction}</span>
                      </div>
                      <div className="text-slate-400">Cheapness: {fmtNum(d.cheapness)} | Score: {fmtNum(d.score)}</div>
                      <div className="text-slate-400">Tail: {fmt$(d.tail)}</div>
                    </div>
                  );
                }}
              />
              <Scatter data={scatterData} fill="#8884d8">
                {scatterData.map((d, i) => (
                  <Cell key={i} fill={CHART_COLORS[d.direction]} fillOpacity={0.8}
                    r={Math.max(4, Math.min(12, d.tail / 1000))} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── Detail Modal ─────────────────────────────── */}
      {selectedTrade && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
          onClick={() => setSelectedTrade(null)}
        >
          <div
            className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <h2 className="text-xl font-bold">{selectedTrade.ticker}</h2>
                <span className={`px-2 py-0.5 rounded text-sm font-medium
                  ${selectedTrade.direction === "call" ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"}`}>
                  {selectedTrade.direction.toUpperCase()}
                </span>
                <span className={`px-2 py-0.5 rounded-full text-sm font-bold
                  ${selectedTrade.score >= 85 ? "bg-yellow-500/20 text-yellow-300"
                    : selectedTrade.score >= 70 ? "bg-emerald-500/20 text-emerald-300"
                    : "bg-blue-500/20 text-blue-300"}`}>
                  Score: {fmtNum(selectedTrade.score)}
                </span>
              </div>
              <button onClick={() => setSelectedTrade(null)} className="text-slate-400 hover:text-slate-200 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Trade Structure */}
            <div className="grid grid-cols-2 gap-4 mb-5">
              <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-4">
                <div className="text-xs text-emerald-400 uppercase tracking-wider mb-2">Long Leg (Buy)</div>
                <div className="text-lg font-bold">${selectedTrade.long_strike}</div>
                <div className="text-sm text-slate-400 mt-1">Exp: {selectedTrade.long_exp}</div>
                <div className="text-sm text-slate-400">Price: ${selectedTrade.long_price} x {selectedTrade.long_qty}</div>
                <div className="text-sm text-slate-300 mt-1 font-medium">
                  Cost: {fmt$(selectedTrade.long_price * selectedTrade.long_qty * 100)}
                </div>
              </div>
              <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-4">
                <div className="text-xs text-red-400 uppercase tracking-wider mb-2">Short Leg (Sell)</div>
                <div className="text-lg font-bold">${selectedTrade.short_strike}</div>
                <div className="text-sm text-slate-400 mt-1">Exp: {selectedTrade.short_exp}</div>
                <div className="text-sm text-slate-400">Price: ${selectedTrade.short_price} x {selectedTrade.short_qty}</div>
                <div className="text-sm text-slate-300 mt-1 font-medium">
                  Credit: {fmt$(selectedTrade.short_price * selectedTrade.short_qty * 100)}
                </div>
              </div>
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
              {[
                { label: "Ratio", value: selectedTrade.ratio },
                { label: "Net Premium", value: fmt$(selectedTrade.net_premium) },
                { label: "Neutrality", value: fmtPct(selectedTrade.premium_neutral_pct) },
                { label: "Tail Payoff", value: fmt$(selectedTrade.tail_payoff) },
              ].map(m => (
                <div key={m.label} className="bg-slate-800 rounded-lg p-3">
                  <div className="text-xs text-slate-500 uppercase">{m.label}</div>
                  <div className="text-base font-semibold mt-0.5">{m.value}</div>
                </div>
              ))}
            </div>

            {/* Cheapness Breakdown */}
            <div className="bg-slate-800 rounded-lg p-4 mb-4">
              <div className="text-xs text-slate-400 uppercase tracking-wider mb-3">Cheapness Analysis</div>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
                <div>
                  <div className="text-slate-500">Composite</div>
                  <div className="font-bold text-lg">{fmtNum(selectedTrade.cheapness)}<span className="text-xs text-slate-500">/100</span></div>
                </div>
                <div>
                  <div className="text-slate-500">Equidistant Ratio</div>
                  <div className="font-semibold">{fmtNum(selectedTrade.equidist_ratio)}x</div>
                </div>
                <div>
                  <div className="text-slate-500">IV / RV</div>
                  <div className={`font-semibold ${selectedTrade.iv_rv < 1 ? "text-emerald-400" : "text-red-400"}`}>
                    {fmtNum(selectedTrade.iv_rv, 2)}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500">Move Yield</div>
                  <div className="font-semibold">{fmtNum(selectedTrade.hist_move_yield, 0)}x</div>
                </div>
              </div>
            </div>

            {/* Greeks */}
            <div className="bg-slate-800 rounded-lg p-4">
              <div className="text-xs text-slate-400 uppercase tracking-wider mb-3">Greeks at Entry</div>
              <div className="grid grid-cols-3 gap-3 text-sm">
                <div>
                  <div className="text-slate-500">Delta</div>
                  <div className="font-semibold">{fmtNum(selectedTrade.net_delta)}</div>
                </div>
                <div>
                  <div className="text-slate-500">Vega</div>
                  <div className="font-semibold">{fmtNum(selectedTrade.net_vega)}</div>
                </div>
                <div>
                  <div className="text-slate-500">Theta</div>
                  <div className={`font-semibold ${selectedTrade.net_theta < 0 ? "text-red-400" : "text-emerald-400"}`}>
                    {fmtNum(selectedTrade.net_theta, 2)}/day
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
