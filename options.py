from flask import Blueprint, request, jsonify
import yfinance as yf
import math

options_bp = Blueprint("options", __name__)

def _safe(val):
    try:
        v = float(val)
        return None if (v != v) else round(v, 4)
    except:
        return None

@options_bp.route("/expirations/<ticker>")
def get_expirations(ticker):
    ticker = ticker.upper().strip()
    try:
        t = yf.Ticker(ticker)
        return jsonify({"symbol": ticker, "expirations": list(t.options)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@options_bp.route("/chain/<ticker>")
def get_chain(ticker):
    ticker   = ticker.upper().strip()
    expiry   = request.args.get("expiry")
    opt_type = request.args.get("type", "both").lower()
    try:
        t            = yf.Ticker(ticker)
        info         = t.info
        current_price= info.get("currentPrice") or info.get("regularMarketPrice", 0)
        expirations  = list(t.options)
        if not expiry:
            expiry = expirations[0] if expirations else None
        if not expiry:
            return jsonify({"error": "No expiry dates available"}), 404
        chain = t.option_chain(expiry)

        def fmt(df, side):
            rows = []
            for _, row in df.iterrows():
                bid = _safe(row.get("bid")) or 0
                ask = _safe(row.get("ask")) or 0
                rows.append({
                    "contractSymbol":    row.get("contractSymbol"),
                    "type":              side,
                    "strike":            _safe(row.get("strike")),
                    "lastPrice":         _safe(row.get("lastPrice")),
                    "bid":               _safe(row.get("bid")),
                    "ask":               _safe(row.get("ask")),
                    "midpoint":          round((bid + ask) / 2, 4),
                    "volume":            int(row.get("volume") or 0),
                    "openInterest":      int(row.get("openInterest") or 0),
                    "impliedVolatility": _safe(row.get("impliedVolatility")),
                    "inTheMoney":        bool(row.get("inTheMoney", False)),
                    "expiry":            expiry,
                })
            return rows

        result = {"symbol": ticker, "expiry": expiry, "currentPrice": current_price}
        if opt_type in ("call", "both"):
            result["calls"] = fmt(chain.calls, "call")
        if opt_type in ("put", "both"):
            result["puts"] = fmt(chain.puts, "put")
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@options_bp.route("/near-money/<ticker>")
def get_near_money(ticker):
    ticker = ticker.upper().strip()
    expiry = request.args.get("expiry")
    width  = int(request.args.get("width", 5))
    try:
        t             = yf.Ticker(ticker)
        current_price = float(t.info.get("currentPrice") or t.info.get("regularMarketPrice", 0))
        expirations   = list(t.options)
        if not expiry:
            expiry = expirations[0]
        chain = t.option_chain(expiry)

        def near(df, side):
            df = df.copy()
            df["dist"] = abs(df["strike"] - current_price)
            df = df.sort_values("dist").head(width * 2)
            return [{
                "type":           side,
                "strike":         _safe(r["strike"]),
                "bid":            _safe(r["bid"]),
                "ask":            _safe(r["ask"]),
                "iv":             _safe(r["impliedVolatility"]),
                "oi":             int(r["openInterest"] or 0),
                "volume":         int(r["volume"] or 0),
                "inTheMoney":     bool(r["inTheMoney"]),
                "expiry":         expiry,
                "contractSymbol": r["contractSymbol"],
            } for _, r in df.iterrows()]

        return jsonify({
            "symbol":       ticker,
            "currentPrice": current_price,
            "expiry":       expiry,
            "calls":        near(chain.calls, "call"),
            "puts":         near(chain.puts,  "put"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@options_bp.route("/iv-rank/<ticker>")
def get_iv_rank(ticker):
    ticker = ticker.upper().strip()
    try:
        hist = yf.Ticker(ticker).history(period="1y", interval="1d")
        hist["log_ret"] = (hist["Close"] / hist["Close"].shift(1)).apply(
            lambda x: math.log(x) if x > 0 else 0
        )
        hist["hv30"] = hist["log_ret"].rolling(30).std() * math.sqrt(252)
        hv      = hist["hv30"].dropna()
        current = float(hv.iloc[-1])
        hv_min  = float(hv.min())
        hv_max  = float(hv.max())
        iv_rank = round((current - hv_min) / (hv_max - hv_min) * 100, 1) if hv_max != hv_min else 50.0
        iv_pct  = round((hv <= current).sum() / len(hv) * 100, 1)
        return jsonify({
            "symbol":       ticker,
            "currentHV30":  round(current * 100, 2),
            "ivRank":       iv_rank,
            "ivPercentile": iv_pct,
            "interpretation": "High IV — good for premium selling" if iv_rank > 50 else "Low IV — good for buying options",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
