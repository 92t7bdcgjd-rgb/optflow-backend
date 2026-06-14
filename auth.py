from flask import Blueprint, request, jsonify

auth_bp = Blueprint("auth", __name__)
_logged_in = False
_username = None


def get_rh():
    try:
        import robin_stocks.robinhood as r
        return r
    except ImportError:
        return None


@auth_bp.route("/login", methods=["POST"])
def login():
    global _logged_in, _username
    data     = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    mfa_code = data.get("mfa_code", "").strip() or None

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    r = get_rh()
    if not r:
        _logged_in = True
        _username  = username
        return jsonify({"success": True, "username": username, "note": "demo_mode"})

    try:
        result = r.login(
            username=username,
            password=password,
            mfa_code=mfa_code,
            store_session=True,
            by_sms=True,
        )
        if result:
            _logged_in = True
            _username  = username
            return jsonify({"success": True, "username": username})
        else:
            return jsonify({"error": "Login failed — check credentials"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@auth_bp.route("/logout", methods=["POST"])
def logout():
    global _logged_in, _username
    r = get_rh()
    try:
        if r:
            r.logout()
    except Exception:
        pass
    _logged_in = False
    _username  = None
    return jsonify({"success": True})


@auth_bp.route("/status", methods=["GET"])
def status():
    return jsonify({"connected": _logged_in, "username": _username})
