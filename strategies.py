from flask import Blueprint, request, jsonify
import yfinance as yf
import math
from datetime import datetime, timedelta

strategies_bp = Blueprint("strategies", __name__)

def _safe(val):
    try:
        v = float(val)
        return None if (v != v) else round(v, 4)
    except:
        return None

def _get_technicals(ticker):
    import ta
    t    = yf.Ticker(ticker)
    hist = t.history(period="3mo", interval="1d")
    if hist.empty:
        return None, None
    close  = hist["Close"]
    high   = hist["High"]
    low    = hist["Low"]
    volume = hist["Volume"]
    rsi    = ta.momentum.RSIIndicator(close, window=14).rsi()
    macd   = ta.trend.MACD(close)
    bb     = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    ema20  = ta.trend.EMAIndicator(close, window=20).ema_indicator()
    sma50  = ta.trend.SMAIndicator(close, window=50).sma_indicator()
    atr    = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()
    return {
        "price":          float(close.iloc[-1]),
        "rsi":            float(rsi.iloc[-1]),
        "macd_hist":      float(macd.macd_diff().iloc[-1]),
        "macd_hist_prev": float(macd.macd_diff().iloc[-2]),
        "bb_upper":       float(bb.bollinger_hband().iloc[-1]),
        "bb_lower":       float(bb.bollinger_lband().iloc[-1]),
        "bb_width":       float(bb.bollinger_wband().iloc[-1]),
        "ema20":          float(ema20.iloc[-1]),
        "sma50":          float(sma50.iloc[-1]),
        "atr":            float(atr.iloc[-1]),
        "volume":         float(volume.iloc[-1]),
        "volume_surge":   float(volume.iloc[-1]) / float(volume.rolling(20).mean().iloc[-1]),
        "high_20d":       float(high.rolling(20).max().iloc[-1]),
        "low_20d":        float(low.rolling(20).min().iloc[-1]),
        "price_5d_ago":   float(close.iloc[-5]) if len(close) >= 5 else float(close.iloc[0]),
    }, t.info

def _nearest_expiry(t, weeks_out=2):
    try:
        opts   = list(t.options)
        target = datetime.now() + timedelta(weeks=weeks_out)
        return min(opts, key=lambda d: abs(datetime.strptime(d, "%Y-%m-%d") - target))
    except:
        return None

def _nearest_strike(df, price):
    try:
        df = df.copy()
        df["dist"] = abs(df["strike"] - price)
        return float(df.sort_values("dist").iloc[0]["strike"])
    except:
        return round(price / 5) * 5

def _premium(df, strike):
    try:
        row = df[df["strike"] == strike].iloc[0]
        bid = float(row.get("bid") or 0)
        ask = float(row.get("ask") or 0)
        return round((bid + ask) / 2, 2) if ask > 0 else round(float(row.get("lastPrice") or 1.0), 2)
    except:
        return None

def _momentum(ticker, s, info, t):
    results = []
    price = s["price"]
    surge = s["volume_surge"]
    mom5d = (price - s["price_5d_ago"]) / s["price_5d_ago"] * 100
    if surge >= 1.5 and price >= s["high_20d"] * 0.99:
        exp = _nearest_expiry(t, 2)
        if exp:
            chain  = t.option_chain(exp)
            strike = _nearest_strike(chain.calls, price)
            prem   = _premium(chain.calls, strike) or round(price * 0.015, 2)
            results.append({
                "strategy":    "Momentum Breakout",
                "action":      "BUY_CALL",
                "strike":      strike,
                "expiry":      exp,
                "contracts":   1,
                "entryPrice":  prem,
                "targetPrice": round(prem * 2.2, 2),
                "stopLoss":    round(prem * 0.45, 2),
                "confidence":  "HIGH" if surge >= 2.0 and mom5d > 3 else "MODERATE",
                "riskReward":  "1:2.2",
                "rationale":   f"Volume {surge:.1f}x avg, price breaking 20-day high ${s['high_20d']:.2f}. Momentum +{mom5d:.1f}% over 5 days.",
            })
    if surge >= 1.5 and price <= s["low_20d"] * 1.01 and mom5d < -2:
        exp = _nearest_expiry(t, 2)
        if exp:
            chain  = t.option_chain(exp)
            strike = _nearest_strike(chain.puts, price)
            prem   = _premium(chain.puts, strike) or round(price * 0.015, 2)
            results.append({
                "strategy":    "Momentum Breakdown",
                "action":      "BUY_PUT",
                "strike":      strike,
                "expiry":      exp,
                "contracts":   1,
                "entryPrice":  prem,
                "targetPrice": round(prem * 2.0, 2),
                "stopLoss":    round(prem * 0.45, 2),
                "confidence":  "MODERATE",
                "riskReward":  "1:2.0",
                "rationale":   f"Volume {surge:.1f}x avg, price breaking below 20-day low ${s['low_20d']:.2f}.",
            })
    return results

def _iv_crush(ticker, s, info, t):
    results = []
    price      = s["price"]
    iv_high    = s["bb_width"] > 0.08
    iv_extreme = s["bb_width"] > 0.14
    earnings_ts = info.get("earningsTimestamp")
    days_to_earnings = None
    if earnings_ts:
        try:
            days_to_earnings = (datetime.fromtimestamp(earnings_ts) - datetime.now()).days
        except:
            pass
    near_earnings = days_to_earnings is not None and 0 <= days_to_earnings <= 7
    if near_earnings and iv_high:
        exp = _nearest_expiry(t, 1)
        if exp:
            chain  = t.option_chain(exp)
            strike = _nearest_strike(chain.calls, price)
            cprem  = _premium(chain.calls, strike) or round(price * 0.02, 2)
            pprem  = _premium(chain.puts,  strike) or round(price * 0.02, 2)
            results.append({
                "strategy":    "Earnings Straddle",
                "action":      "BUY_CALL",
                "strike":      strike,
                "expiry":      exp,
                "contracts":   1,
                "entryPrice":  cprem,
                "targetPrice": round(cprem * 2.5, 2),
                "stopLoss":    round(cprem * 0.4, 2),
                "confidence":  "HIGH" if iv_extreme else "MODERATE",
                "riskReward":  "1:2.5",
                "rationale":   f"Earnings in {days_to_earnings} day(s). IV elevated (BB {s['bb_width']:.1%}). Straddle cost ${cprem+pprem:.2f}.",
            })
    elif iv_high and not near_earnings:
        exp = _nearest_expiry(t, 2)
        if exp:
            chain      = t.option_chain(exp)
            otm_strike = round((price * 1.05) / 5) * 5
            prem       = _premium(chain.calls, otm_strike) or round(price * 0.008, 2)
            if prem and prem > 0.3:
                results.append({
                    "strategy":    "IV Crush — Sell OTM Call",
                    "action":      "SELL_CALL",
                    "strike":      otm_strike,
                    "expiry":      exp,
                    "contracts":   1,
                    "entryPrice":  prem,
                    "targetPrice": round(prem * 0.25, 2),
                    "stopLoss":    round(prem * 2.0, 2),
                    "confidence":  "MODERATE",
                    "riskReward":  "1:0.75",
                    "rationale":   f"IV elevated (BB {s['bb_width']:.1%}) without catalyst. Sell OTM call to collect premium.",
                })
    return results

def _trend(ticker, s, info, t):
    results = []
    price  = s["price"]
    rsi    = s["rsi"]
    macd_h = s["macd_hist"]
    macd_p = s["macd_hist_prev"]
    ema20  = s["ema20"]
    sma50  = s["sma50"]
    crossed_up   = macd_h > 0 and macd_p <= 0
    crossed_down = macd_h < 0 and macd_p >= 0
    if crossed_up and price > ema20 and price > sma50 and 40 < rsi < 70:
        exp = _nearest_expiry(t, 3)
        if exp:
            chain  = t.option_chain(exp)
            strike = round((price * 1.02) / 5) * 5
            prem   = _premium(chain.calls, strike) or round(price * 0.012, 2)
            results.append({
                "strategy":    "Trend Follow — Bullish",
                "action":      "BUY_CALL",
                "strike":      strike,
                "expiry":      exp,
                "contracts":   1,
                "entryPrice":  prem,
                "targetPrice": round(prem * 2.5, 2),
                "stopLoss":    round(prem * 0.4, 2),
                "confidence":  "HIGH",
                "riskReward":  "1:2.5",
                "rationale":   f"MACD bullish crossover. Above EMA20 ${ema20:.2f} and SMA50 ${sma50:.2f}. RSI {rsi:.0f}.",
            })
    if crossed_down and price < ema20 and price < sma50 and 30 < rsi < 60:
        exp = _nearest_expiry(t, 3)
        if exp:
            chain  = t.option_chain(exp)
            strike = round((price * 0.98) / 5) * 5
            prem   = _premium(chain.puts, strike) or round(price * 0.012, 2)
            results.append({
                "strategy":    "Trend Follow — Bearish",
                "action":      "BUY_PUT",
                "strike":      strike,
                "expiry":      exp,
                "contracts":   1,
                "entryPrice":  prem,
                "targetPrice": round(prem * 2.5, 2),
                "stopLoss":    round(prem * 0.4, 2),
                "confidence":  "HIGH",
                "riskReward":  "1:2.5",
                "rationale":   f"MACD bearish crossover. Below EMA20 ${ema20:.2f} and SMA50 ${sma50:.2f}. RSI {rsi:.0f}.",
            })
    if rsi < 32 and price > sma50:
        exp = _nearest_expiry(t, 2)
        if exp:
            chain  = t.option_chain(exp)
            strike = _nearest_strike(chain.calls, price)
            prem   = _premium(chain.calls, strike) or round(price * 0.015, 2)
            results.append({
                "strategy":    "RSI Oversold Bounce",
                "action":      "BUY_CALL",
                "strike":      strike,
                "expiry":      exp,
                "contracts":   1,
                "entryPrice":  prem,
                "targetPrice": round(prem * 2.0, 2),
                "stopLoss":    round(prem * 0.45, 2),
                "confidence":  "MODERATE",
                "riskReward":  "1:2.0",
                "rationale":   f"RSI {rsi:.0f} oversold while above SMA50 ${sma50:.2f}. Mean-reversion bounce.",
            })
    return results

@strategies_bp.route("/analyze/<ticker>")
def analyze(ticker):
    ticker    = ticker.upper().strip()
    requested = request.args.get("strategies", "momentum,iv_crush,trend").split(",")
    try:
        t = yf.Ticker(ticker)
        sigs, info = _get_technicals(ticker)
        if sigs is None:
            return jsonify({"error": f"No data for {ticker}"}), 404
        all_signals = []
        if "momentum" in requested:
            all_signals.extend(_momentum(ticker, sigs, info, t))
        if "iv_crush" in requested:
            all_signals.extend(_iv_crush(ticker, sigs, info, t))
        if "trend" in requested:
            all_signals.extend(_trend(ticker, sigs, info, t))
        order = {"HIGH": 0, "MODERATE": 1, "LOW": 2}
        all_signals.sort(key=lambda s: order.get(s.get("confidence", "LOW"), 2))
        return jsonify({
            "symbol":     ticker,
            "price":      sigs["price"],
            "analyzedAt": datetime.utcnow().isoformat() + "Z",
            "signals":    all_signals,
            "technicals": {
                "rsi":      round(sigs["rsi"], 1),
                "macdHist": round(sigs["macd_hist"], 4),
                "ema20":    round(sigs["ema20"], 2),
                "sma50":    round(sigs["sma50"], 2),
                "bbWidth":  round(sigs["bb_width"], 4),
                "volSurge": round(sigs["volume_surge"], 2),
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@strategies_bp.route("/scan", methods=["POST"])
def scan():
    data       = request.json or {}
    tickers    = [t.upper().strip() for t in data.get("tickers", [])]
    strategies = data.get("strategies", ["momentum", "iv_crush", "trend"])
    results, errors = [], []
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            sigs, info = _get_technicals(ticker)
            if sigs is None:
                errors.append({"ticker": ticker, "error": "No data"})
                continue
            signals = []
            if "momentum" in strategies: signals.extend(_momentum(ticker, sigs, info, t))
            if "iv_crush"  in strategies: signals.extend(_iv_crush(ticker, sigs, info, t))
            if "trend"     in strategies: signals.extend(_trend(ticker, sigs, info, t))
            for s in signals:
                s["ticker"] = ticker
                s["price"]  = sigs["price"]
            results.extend(signals)
        except Exception as e:
            errors.append({"ticker": ticker, "error": str(e)})
    order = {"HIGH": 0, "MODERATE": 1, "LOW": 2}
    results.sort(key=lambda s: order.get(s.get("confidence", "LOW"), 2))
    return jsonify({"signals": results, "totalCount": len(results), "errors": errors})
