import os
from flask import Flask, jsonify, request, send_from_directory
import db
import bot

# Initialize Flask App
app = Flask(__name__, static_folder='static', static_url_path='')

@app.route('/')
def index():
    """Serves the main dashboard page."""
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/state', methods=['GET'])
def get_state():
    """Returns the safe dashboard state (secrets filtered out)."""
    return jsonify(db.get_safe_state())

@app.route('/api/toggle-trading', methods=['POST'])
def toggle_trading():
    """Toggles the bot's trade scanning loop on/off."""
    data = request.get_json() or {}
    status = data.get("status", False)
    action = data.get("action", "soft_stop")
    
    if not status and action == "hard_stop":
        db.add_log("[API Command] Hard Stop: Toggling trading active OFF and liquidating all positions.")
        bot.force_close_all_positions()
        
    safe_state = db.set_trading_active(status)
    return jsonify(safe_state)

@app.route('/api/watchlist/add', methods=['POST'])
def watchlist_add():
    """Adds a new token symbol to the currently selected active watchlist."""
    data = request.get_json() or {}
    symbol = data.get("symbol", "").strip()
    if not symbol:
        return jsonify({"error": "Symbol is required"}), 400
        
    safe_state = db.add_to_watchlist(symbol)
    return jsonify(safe_state)

@app.route('/api/watchlist/remove', methods=['POST'])
def watchlist_remove():
    """Removes a token symbol from the currently selected active watchlist."""
    data = request.get_json() or {}
    symbol = data.get("symbol", "").strip()
    if not symbol:
        return jsonify({"error": "Symbol is required"}), 400
        
    safe_state = db.remove_from_watchlist(symbol)
    return jsonify(safe_state)

@app.route('/api/watchlist/create', methods=['POST'])
def watchlist_create():
    """Creates a new named watchlist for the active account."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Watchlist name is required"}), 400
        
    try:
        safe_state = db.create_watchlist(name)
        bot.restart()
        return jsonify(safe_state)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/watchlist/delete', methods=['POST'])
def watchlist_delete():
    """Deletes a named watchlist for the active account."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Watchlist name is required"}), 400
        
    try:
        safe_state = db.delete_watchlist(name)
        bot.restart()
        return jsonify(safe_state)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/watchlist/select', methods=['POST'])
def watchlist_select():
    """Selects the active watchlist for the active account."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Watchlist name is required"}), 400
        
    try:
        safe_state = db.select_watchlist(name)
        bot.restart()
        return jsonify(safe_state)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/watchlist/rename', methods=['POST'])
def watchlist_rename_endpoint():
    """Renames a global watchlist. Updates all accounts that referenced the old name."""
    data = request.get_json() or {}
    old_name = data.get("oldName", "").strip()
    new_name = data.get("newName", "").strip()
    if not old_name or not new_name:
        return jsonify({"error": "Both oldName and newName are required"}), 400
    try:
        safe_state = db.rename_watchlist(old_name, new_name)
        bot.restart()
        return jsonify(safe_state)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Updates active account's trade limits, total balance, and the global Google Sheets Webhook URL."""
    data = request.get_json() or {}
    max_trades = data.get("maxTrades", 5)
    allocated_capital = data.get("allocatedCapital", 500.0)
    sheets_url = data.get("googleSheetsWebhookUrl", "")
    total_balance = data.get("totalBalance", None)
    
    safe_state = db.update_settings(max_trades, allocated_capital, sheets_url, total_balance)
    return jsonify(safe_state)

@app.route('/api/accounts/add', methods=['POST'])
def add_account():
    """Registers a new account profile (Paper or Real API Key profile)."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    mode = data.get("mode", "paper").strip()
    api_key = data.get("apiKey", "").strip()
    api_secret = data.get("apiSecret", "").strip()
    initial_balance = data.get("initialBalance", 1000.0)
    
    if not name:
        return jsonify({"error": "Account Name is required"}), 400
        
    if mode == "real":
        if not api_key or not api_secret:
            return jsonify({"error": "API Key and Secret are required for Real accounts."}), 400
            
        # Instantly ping Binance using the provided credentials
        validation = bot.ping_exchange(api_key, api_secret, "real")
        if validation.get("status") != "CONNECTED":
            err_msg = validation.get("details", "Failed to connect to Binance.")
            return jsonify({"error": f"API Validation Failed: {err_msg}"}), 400
            
    try:
        safe_state = db.add_account(name, mode, api_key, api_secret, initial_balance)
        return jsonify(safe_state)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/accounts/delete', methods=['POST'])
def delete_account():
    """Removes an account profile from the database."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    
    try:
        safe_state = db.delete_account(name)
        return jsonify(safe_state)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/accounts/select', methods=['POST'])
def select_account():
    """
    Selects the active account. 
    Restarts the bot loop so the candle fetcher switches context immediately.
    """
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    
    try:
        safe_state = db.set_active_account(name)
        # Restart the background trading loop
        bot.restart()
        return jsonify(safe_state)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/positions/close', methods=['POST'])
def close_position():
    """Manually triggers market exit/liquidation for a single open position."""
    data = request.get_json() or {}
    symbol = data.get("symbol", "").strip()
    
    if not symbol:
        return jsonify({"error": "Symbol is required"}), 400
        
    success = bot.force_close_position(symbol)
    if success:
        return jsonify(db.get_safe_state())
    else:
        return jsonify({"error": f"Failed to close position for {symbol}. Make sure it is active and pricing is online."}), 500

@app.route('/api/positions/close-all', methods=['POST'])
def close_all_positions():
    """Manually market liquidates all active open positions in the active profile."""
    bot.force_close_all_positions()
    return jsonify(db.get_safe_state())

@app.route('/api/exchange-status', methods=['GET'])
def exchange_status():
    """Returns cached exchange status instantly — no blocking Binance calls here."""
    active = db.get_active_account()
    if not active:
        return jsonify({
            "status": "NO_ACCOUNT",
            "exchange": "—",
            "latency_ms": None,
            "details": "No active account configured. Create an account in the Control Panel.",
            "streaming": False,
            "accountName": None,
            "mode": None
        })

    # Return cached result immediately — exchange monitor thread keeps this fresh every 30s
    cached = bot.get_cached_exchange_status()
    cached["accountName"] = active.get("name")
    cached["mode"] = active.get("mode")
    return jsonify(cached)

@app.route('/api/exchange-status/force', methods=['POST'])
def exchange_status_force():
    """Forces an immediate Binance re-check and returns the fresh result."""
    active = db.get_active_account()
    if not active:
        return jsonify({"status": "NO_ACCOUNT", "details": "No active account."}), 400

    result = bot.ping_exchange(
        api_key=active.get("apiKey", ""),
        api_secret=active.get("apiSecret", ""),
        mode=active.get("mode", "paper")
    )
    bot._update_exchange_cache(result)
    result["accountName"] = active.get("name")
    result["mode"] = active.get("mode")
    return jsonify(result)

@app.route('/api/holdings', methods=['GET'])
def get_holdings():
    """Returns all Binance asset holdings with USD values for real accounts."""
    active = db.get_active_account()
    if not active:
        return jsonify({"error": "No active account"}), 400
    if active.get("mode") != "real":
        return jsonify({"holdings": [], "mode": "paper", "message": "Holdings only available for Real accounts."})
    
    api_key = active.get("apiKey", "")
    api_secret = active.get("apiSecret", "")
    holdings = bot.fetch_all_holdings(api_key, api_secret)
    return jsonify(holdings)

@app.route('/api/holdings/sell', methods=['POST'])
def sell_holding():
    """Manually sells a specified percentage or USD value of a held asset at market price."""
    active = db.get_active_account()
    if not active:
        return jsonify({"error": "No active account"}), 400
    if active.get("mode") != "real":
        return jsonify({"error": "Manual sell only available for Real accounts."}), 400

    data = request.get_json() or {}
    asset = data.get("asset", "").strip().upper()
    mode = data.get("mode", "pct").strip().lower() # 'pct' or 'usd'
    value = float(data.get("value", 100.0))

    if not asset:
        return jsonify({"error": "Asset is required"}), 400
    if value <= 0:
        return jsonify({"error": "Value must be greater than 0"}), 400

    result = bot.manual_sell_holding(active, asset, mode, value)
    return jsonify(result)

if __name__ == '__main__':
    # Initialize JSON Database (automatic loading now handled inside db.py, but explicit init called for safety)
    db.init()
    
    # Start background bot scanning thread
    bot.start()
    
    # Start background exchange status monitor thread (polls Binance every 30s, serves cache instantly)
    bot.start_exchange_monitor()
    
    # Get host and port from environment (Render injects PORT, default to 0.0.0.0 for external access)
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", os.environ.get("BOT_PORT", 5000)))
    
    print("\n" + "="*60)
    print(f"  CRYPTO SPOT SCALPING BOT SERVED AT http://{host}:{port}")
    print("="*60 + "\n")
    
    # IMPORTANT: threaded=True so Binance API calls (13s) don't block UI state polls
    app.run(host=host, port=port, debug=False, threaded=True)
