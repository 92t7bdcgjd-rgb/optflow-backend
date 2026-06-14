import os
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

try:
    from routes.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
except Exception as e:
    print(f"Warning: auth routes failed: {e}")

try:
    from routes.market import market_bp
    app.register_blueprint(market_bp, url_prefix="/api/market")
except Exception as e:
    print(f"Warning: market routes failed: {e}")

try:
    from routes.options import options_bp
    app.register_blueprint(options_bp, url_prefix="/api/options")
except Exception as e:
    print(f"Warning: options routes failed: {e}")

try:
    from routes.orders import orders_bp
    app.register_blueprint(orders_bp, url_prefix="/api/orders")
except Exception as e:
    print(f"Warning: orders routes failed: {e}")

try:
    from routes.strategies import strategies_bp
    app.register_blueprint(strategies_bp, url_prefix="/api/strategies")
except Exception as e:
    print(f"Warning: strategies routes failed: {e}")

@app.route("/")
def index():
    return jsonify({"app": "OPTFLOW", "status": "running"})

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "1.0.0"})

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
