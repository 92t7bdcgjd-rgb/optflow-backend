from flask import Blueprint, request, jsonify
import yfinance as yf
import math

market_bp = Blueprint("market", __name__)

def _safe(val):
    try:
        v = float(val)
        return None if (v != v) else round(v, 4)
    except:
        return None

@market_bp.route("/quote/<ticker>")
def get_quote(ticker):
    ticker = ticker.upper().strip()
    try:
        t = yf.Ticker(ticker)
        info = t.info
        price = _safe(info.get("currentPrice") or info.get("regularMarketPrice"))
        prev  = _safe(info.get("previousClose") or info.get("regularMarketPreviousClose"))
        change = round(price - prev, 4) if price and prev else None
        changePct = round((change / prev) * 100, 4) if change and prev else None
        return jsonify({
            "symbol": ticker,
            "name": info.get("longName") or info.get("shortName", ticker),
            "price": price,
            "previousClose": prev,
            "change": change,
            "changePct": changePct,
            "open": _safe(info.get("open")),
            "dayHigh": _safe(info.get("dayHigh")),
            "dayLow": _safe(info.get("dayLow")),
            "volume": info.get("volume"),
            "avgVolume": info.get("averageVolume"),
            "marketCap": info.get("marketCap"),
            "week52High": _safe(info.get("fiftyTwoWeekHigh")),
            "week52Low": _safe(info.get("fiftyTwoWeekLow")),
            "impliedVolatility": _safe(info.get("impliedVolatility")),
            "beta": _safe(info.get("beta")),
            "pe": _safe(info.get("trailingPE")),
            "sector": info.get("sector"),
            "earningsDate": str(info.get("earningsTimestamp", "")),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@market_bp.route("/history/<ticker>")
def get_history(ticker):
    ticker   = ticker.upper().strip()
    period   = request.args.get("period", "1d")
    interval = request.args.get("interval", "5m")
    try:
        hist = yf.Ticker(ticker).history(period=period, interval=interval)
        candles = [{
            "time":   str(ts),
            "open":   round(float(row["Open"]), 4),
            "high":   round(float(row["High"]), 4),
            "low":    round(float(row["Low"]), 4),
            "close":  round(float(row["Close"]), 4),
            "volume": int(row["Volume"]),
        } for ts, row in hist.iterrows()]
        return jsonify({"symbol": ticker, "candles": candles})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@market_bp.route("/technicals/<ticker>")
def get_technicals(ticker):
    ticker = ticker.upper().strip()
    try:
        import ta
        t    = yf.Ticker(ticker)
        hist = t.history(period="3mo", interval="1d")
        close = hist["Close"]
        high  = hist["High"]
        low   = hist["Low"]
        rsi   = ta.momentum.RSIIndicator(close, window=14).rsi()
        macd  = ta.trend.MACD(close)
        bb    = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        ema20 = ta.trend.EMAIndicator(close, window=20).ema_indicator()
        sma50 = ta.trend.SMAIndicator(close, window=50).sma_indicator()
        atr   = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()
        price = float(close.iloc[-1])
        return jsonify({
            "symbol": ticker,
            "currentPrice": round(price, 4),
            "rsi": round(float(rsi.iloc[-1]), 2),
            "macd": {
                "macd":      round(float(macd.macd().iloc[-1]), 4),
                "signal":    round(float(macd.macd_signal().iloc[-1]), 4),
                "histogram": round(float(macd.macd_diff().iloc[-1]), 4),
            },
            "bollingerBands": {
                "upper":  round(float(bb.bollinger_hband().iloc[-1]), 4),
                "middle": round(float(bb.bollinger_mavg().iloc[-1]), 4),
                "lower":  round(float(bb.bollinger_lband().iloc[-1]), 4),
                "width":  round(float(bb.bollinger_wband().iloc[-1]), 4),
            },
            "ema20":  round(float(ema20.iloc[-1]), 4),
            "sma50":  round(float(sma50.iloc[-1]), 4),
            "atr":    round(float(atr.iloc[-1]), 4),
            "signals": {
                "rsi_oversold":   float(rsi.iloc[-1]) < 30,
                "rsi_overbought": float(rsi.iloc[-1]) > 70,
                "above_ema20":    price > float(ema20.iloc[-1]),
                "above_sma50":    price > float(sma50.iloc[-1]),
                "macd_bullish":   float(macd.macd_diff().iloc[-1]) > 0,
                "bb_squeeze":     float(bb.bollinger_wband().iloc[-1]) < 0.1,
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
