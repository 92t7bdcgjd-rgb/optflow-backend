from flask import Blueprint, request, jsonify
from datetime import datetime

orders_bp = Blueprint("orders", __name__)
_order_log = []


def get_rh():
    try:
        import robin_stocks.robinhood as r
        return r
    except ImportError:
        return None


@orders_bp.route("/place", methods=["POST"])
def place_order():
    data        = request.json or {}
    ticker      = data.get("ticker", "").upper().strip()
    action      = data.get("action", "").upper()
    strike      = float(data.get("strike", 0))
    expiry      = data.get("expiry", "")
    contracts   = int(data.get("contracts", 1))
    limit_price = float(data.get("limitPrice", 0))
    order_effect= data.get("orderEffect", "open")

    if not all([ticker, action, strike, expiry, limit_price]):
        return jsonify({"error": "Missing required fields"}), 400

    r           = get_rh()
    option_type = "call" if "CALL" in action else "put"
    side        = "buy" if action.startswith("BUY") else "sell"
    direction   = "debit" if side == "buy" else "credit"

    if not r:
        entry = {
            "id":        f"demo_{len(_order_log)+1}",
            "ticker":    ticker,
            "action":    action,
            "strike":    strike,
            "expiry":    expiry,
            "contracts": contracts,
            "limitPrice":limit_price,
            "status":    "demo_only",
            "rhOrderId": "N/A",
            "placedAt":  datetime.utcnow().isoformat() + "Z",
            "note":      "Demo mode — not sent to Robinhood",
        }
        _order_log.insert(0, entry)
        return jsonify({"success": True, "order": entry})

    try:
        if side == "buy":
            result = r.orders.order_buy_option_limit(
                positionEffect=order_effect,
                creditOrDebit=direction,
                price=limit_price,
                symbol=ticker,
                quantity=contracts,
                expirationDate=expiry,
                strike=strike,
                optionType=option_type,
            )
        else:
            result = r.orders.order_sell_option_limit(
                positionEffect=order_effect,
                creditOrDebit=direction,
                price=limit_price,
                symbol=ticker,
                quantity=contracts,
                expirationDate=expiry,
                strike=strike,
                optionType=option_type,
            )
        entry = {
            "id":        result.get("id"),
            "ticker":    ticker,
            "action":    action,
            "strike":    strike,
            "expiry":    expiry,
            "contracts": contracts,
            "limitPrice":limit_price,
            "status":    result.get("state", "queued"),
            "rhOrderId": result.get("id"),
            "placedAt":  datetime.utcnow().isoformat() + "Z",
        }
        _order_log.insert(0, entry)
        return jsonify({"success": True, "order": entry})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@orders_bp.route("/cancel/<order_id>", methods=["POST"])
def cancel_order(order_id):
    r = get_rh()
    if not r:
        return jsonify({"error": "robin_stocks not available"}), 503
    try:
        result = r.orders.cancel_option_order(order_id)
        for o in _order_log:
            if o.get("rhOrderId") == order_id:
                o["status"] = "cancelled"
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@orders_bp.route("/all", methods=["GET"])
def get_all_orders():
    r = get_rh()
    if not r:
        return jsonify({"orders": _order_log, "count": len(_order_log), "note": "demo_mode"})
    try:
        rh_orders = r.orders.get_all_option_orders() or []
        formatted = []
        for o in rh_orders:
            legs = o.get("legs", [{}])
            leg  = legs[0] if legs else {}
            formatted.append({
                "id":         o.get("id"),
                "ticker":     o.get("chain_symbol"),
                "state":      o.get("state"),
                "price":      o.get("price"),
                "quantity":   o.get("quantity"),
                "side":       leg.get("side"),
                "optionType": leg.get("option_type"),
                "strike":     leg.get("strike_price"),
                "expiry":     leg.get("expiration_date"),
                "createdAt":  o.get("created_at"),
            })
        return jsonify({"orders": formatted, "count": len(formatted)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@orders_bp.route("/open", methods=["GET"])
def get_open_orders():
    r = get_rh()
    if not r:
        open_orders = [o for o in _order_log if o.get("status") not in ("cancelled", "filled")]
        return jsonify({"orders": open_orders, "count": len(open_orders), "note": "demo_mode"})
    try:
        all_orders  = r.orders.get_all_option_orders() or []
        open_orders = [o for o in all_orders if o.get("state") in ("queued", "unconfirmed", "confirmed", "partially_filled")]
        return jsonify({"orders": open_orders, "count": len(open_orders)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@orders_bp.route("/positions", methods=["GET"])
def get_positions():
    r = get_rh()
    if not r:
        return jsonify({"positions": [], "count": 0, "note": "demo_mode"})
    try:
        positions = r.account.get_open_option_positions() or []
        formatted = []
        for pos in positions:
            avg_price = float(pos.get("average_price") or 0)
            quantity  = float(pos.get("quantity") or 0)
            formatted.append({
                "ticker":    pos.get("chain_symbol"),
                "type":      pos.get("type"),
                "quantity":  quantity,
                "avgPrice":  avg_price,
                "costBasis": round(avg_price * quantity * 100, 2),
                "createdAt": pos.get("created_at"),
            })
        return jsonify({"positions": formatted, "count": len(formatted)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@orders_bp.route("/local-log", methods=["GET"])
def get_local_log():
    return jsonify({"orders": _order_log, "count": len(_order_log)})
