import threading
import random
import time
import requests
import hmac
import hashlib
from datetime import datetime
import db
import strategies
import indicators
import sheets

def _request_with_retry(url, max_attempts=3, backoff=1.5):
    """Attempt a GET request with exponential back‑off.
    Returns JSON on success or None on failure.
    Logs specific network errors for user visibility.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            res = requests.get(url, timeout=8)
            if res.status_code == 200:
                return res.json()
            db.add_log(f"[API Error] {url} returned {res.status_code}")
        except requests.exceptions.ConnectionError as e:
            db.add_log(f"[Network Error] Unable to connect to {url}: {e}. Check internet connection.")
            break
        except Exception as e:
            db.add_log(f"[API Error] Attempt {attempt}/{max_attempts} – {e}")
        if attempt < max_attempts:
            time.sleep(backoff * (2 ** (attempt - 1)) + random.random())
    return None

# Threading controls
bot_thread = None
risk_thread = None
stop_event = threading.Event()
last_tick_time = 0
TICK_INTERVAL = 900  # 15 minutes in seconds (matches 15m candlestick timeframe)

# --- EXCHANGE STATUS CACHE ---
_exchange_status_lock = threading.Lock()
_exchange_status_cache = {
    "status": "CHECKING",
    "exchange": "—",
    "latency_ms": None,
    "details": "Initializing exchange connection check…",
    "streaming": False,
    "lastChecked": None
}
_exchange_monitor_thread = None
_exchange_monitor_stop = threading.Event()
EXCHANGE_CHECK_INTERVAL = 30

def get_cached_exchange_status():
    with _exchange_status_lock:
        return dict(_exchange_status_cache)

def _update_exchange_cache(result):
    with _exchange_status_lock:
        _exchange_status_cache.clear()
        _exchange_status_cache.update(result)
        _exchange_status_cache["lastChecked"] = datetime.now().strftime("%H:%M:%S")

def _exchange_monitor_loop():
    db.add_log("[Exchange Monitor] Background connectivity monitor started.")
    while not _exchange_monitor_stop.is_set():
        active = db.get_active_account()
        if active:
            result = ping_exchange(
                api_key=active.get("apiKey", ""),
                api_secret=active.get("apiSecret", ""),
                mode=active.get("mode", "paper")
            )
            _update_exchange_cache(result)
            status = result.get("status", "UNKNOWN")
            latency = result.get("latency_ms")
            lat_str = f"{latency}ms" if latency is not None else "N/A"
            db.add_log(f"[Exchange Monitor] Status: {status} | Latency: {lat_str} | Account: {active.get('name')}")
        else:
            _update_exchange_cache({
                "status": "NO_ACCOUNT",
                "exchange": "—",
                "latency_ms": None,
                "details": "No active account configured.",
                "streaming": False
            })
        for _ in range(EXCHANGE_CHECK_INTERVAL):
            if _exchange_monitor_stop.is_set():
                break
            time.sleep(1)
    db.add_log("[Exchange Monitor] Background monitor stopped.")

def start_exchange_monitor():
    global _exchange_monitor_thread, _exchange_monitor_stop
    if _exchange_monitor_thread is not None and _exchange_monitor_thread.is_alive():
        return
    _exchange_monitor_stop.clear()
    _exchange_monitor_thread = threading.Thread(target=_exchange_monitor_loop, daemon=True)
    _exchange_monitor_thread.start()

def stop_exchange_monitor():
    global _exchange_monitor_thread
    _exchange_monitor_stop.set()
    if _exchange_monitor_thread:
        _exchange_monitor_thread.join(timeout=3)
        _exchange_monitor_thread = None

def start():
    global bot_thread, stop_event, risk_thread
    if bot_thread is not None and bot_thread.is_alive():
        db.add_log("[System] Bot scanner is already running.")
        return
    stop_event.clear()
    
    bot_thread = threading.Thread(target=bot_loop)
    bot_thread.daemon = True
    bot_thread.start()
    
    risk_thread = threading.Thread(target=risk_monitor_loop)
    risk_thread.daemon = True
    risk_thread.start()
    
    db.add_log("[System] Bot background thread and Real-time Risk Monitor started.")

def stop():
    global bot_thread, stop_event, risk_thread
    if bot_thread is None or not bot_thread.is_alive():
        db.add_log("[System] Bot scanner is not running.")
        return
    stop_event.set()
    
    bot_thread.join(timeout=3)
    bot_thread = None
    
    if risk_thread is not None and risk_thread.is_alive():
        risk_thread.join(timeout=3)
    risk_thread = None
    
    db.add_log("[System] Bot background thread and Risk Monitor stopped.")

def restart():
    db.add_log("[System] Restarting bot loop...")
    stop()
    start()

def risk_monitor_loop():
    db.add_log("[System] Real-time Risk Monitor loop initiated.")
    while not stop_event.is_set():
        try:
            run_risk_monitor(check_manual_sells=False)
        except Exception as e:
            db.add_log(f"[Risk Monitor Error] Exception in risk monitor: {e}")
        # Poll every 2 seconds for high responsiveness
        for _ in range(2):
            if stop_event.is_set():
                break
            time.sleep(1)

def bot_loop():
    global last_tick_time
    db.add_log("[System] Bot loop initiated.")
    try:
        run_scan_tick()
    except Exception as e:
        db.add_log(f"[System Error] Initial scan failed: {e}")
    last_tick_time = time.time()
    while not stop_event.is_set():
        time.sleep(1)
        now = time.time()
        if now - last_tick_time >= TICK_INTERVAL:
            try:
                run_scan_tick()
            except Exception as e:
                db.add_log(f"[System Error] Scan tick execution failed: {e}")
            last_tick_time = now

def fetch_binance_balances(api_key, api_secret):
    if not api_key or not api_secret:
        return None
    try:
        timestamp = int(time.time() * 1000)
        query_string = f"timestamp={timestamp}"
        signature = hmac.new(api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        url = f"https://api.binance.com/api/v3/account?{query_string}&signature={signature}"
        headers = {"X-MBX-APIKEY": api_key}
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            data = res.json()
            balances = data.get("balances", [])
            balances_dict = {}
            for bal in balances:
                asset = bal.get("asset", "").upper()
                if asset:
                    free = float(bal.get("free", 0.0))
                    locked = float(bal.get("locked", 0.0))
                    balances_dict[asset] = {"free": free, "locked": locked}
            return balances_dict
        else:
            db.add_log(f"[Exchange API Error] Failed to fetch Binance balances: status {res.status_code}")
            return None
    except Exception as e:
        db.add_log(f"[Exchange API Error] Exception while fetching Binance balances: {e}")
        return None

def fetch_binance_balance(api_key, api_secret):
    balances = fetch_binance_balances(api_key, api_secret)
    if balances is not None:
        usdt_info = balances.get("USDT", {"free": 0.0, "locked": 0.0})
        return round(usdt_info["free"] + usdt_info["locked"], 2)
    return None

def fetch_all_binance_prices():
    url = "https://api.binance.com/api/v3/ticker/price"
    data = _request_with_retry(url)
    if not data:
        return {}
    prices = {}
    for item in data:
        symbol = item.get("symbol")
        price = item.get("price")
        if symbol and price:
            try:
                prices[symbol] = float(price)
            except:
                pass
    return prices

def ping_exchange(api_key="", api_secret="", mode="paper"):
    if mode == "paper":
        return {
            "status": "SIMULATED",
            "exchange": "Paper Engine",
            "latency_ms": 0,
            "details": "Running in Paper Trading mode. No real exchange connection.",
            "streaming": True
        }
    if not api_key or not api_secret:
        return {
            "status": "NO_CREDENTIALS",
            "exchange": "Binance Spot",
            "latency_ms": None,
            "details": "API Key or Secret is missing. Add credentials to connect.",
            "streaming": False
        }
    try:
        import time as _time
        t0 = _time.time()
        ping_res = requests.get("https://api.binance.com/api/v3/ping", timeout=5)
        latency_ms = round((_time.time() - t0) * 1000)
        if ping_res.status_code != 200:
            return {
                "status": "EXCHANGE_UNREACHABLE",
                "exchange": "Binance Spot",
                "latency_ms": None,
                "details": f"Binance returned HTTP {ping_res.status_code}.",
                "streaming": False
            }
        timestamp = int(_time.time() * 1000)
        query_string = f"timestamp={timestamp}"
        signature = hmac.new(api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        headers = {"X-MBX-APIKEY": api_key}
        acc_res = requests.get(
            f"https://api.binance.com/api/v3/account?{query_string}&signature={signature}",
            headers=headers, timeout=8
        )
        if acc_res.status_code == 200:
            data = acc_res.json()
            permissions = data.get("permissions", [])
            can_trade = data.get("canTrade", False)
            return {
                "status": "CONNECTED",
                "exchange": "Binance Spot",
                "latency_ms": latency_ms,
                "details": f"API validated. Permissions: {', '.join(permissions)}. Trade enabled: {can_trade}.",
                "streaming": True,
                "canTrade": can_trade,
                "permissions": permissions
            }
        elif acc_res.status_code in (401, 400):
            res_data = acc_res.json()
            err_msg = res_data.get("msg", "Unknown error")
            err_code = res_data.get("code", 0)
            if err_code == -1021:
                details = "System time is out of sync with Binance servers! Please synchronize your Windows clock in Date & Time Settings."
            else:
                details = f"API Key rejected by Binance: {err_msg}"
            return {
                "status": "API_KEY_ERROR",
                "exchange": "Binance Spot",
                "latency_ms": latency_ms,
                "details": details,
                "streaming": False
            }
        else:
            return {
                "status": "API_ERROR",
                "exchange": "Binance Spot",
                "latency_ms": latency_ms,
                "details": f"Unexpected response: HTTP {acc_res.status_code}.",
                "streaming": False
            }
    except requests.exceptions.ConnectionError:
        return {
            "status": "OFFLINE",
            "exchange": "Binance Spot",
            "latency_ms": None,
            "details": "Cannot reach Binance servers. Check your internet connection.",
            "streaming": False
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "exchange": "Binance Spot",
            "latency_ms": None,
            "details": f"Unexpected error: {str(e)}",
            "streaming": False
        }

def run_risk_monitor(check_manual_sells=False):
    """
    Monitors all open positions for Stop Loss or Take Profit target triggers.
    Runs every 2 seconds in a background thread for real-time risk control.
    """
    active_acc = db.get_active_account()
    if not active_acc:
        return False
        
    order_executed = False
    real_balances = None
    if check_manual_sells and active_acc.get("mode") == "real":
        api_key = active_acc.get("apiKey", "")
        api_secret = active_acc.get("apiSecret", "")
        if api_key and api_secret:
            real_balances = fetch_binance_balances(api_key, api_secret)
            
    open_positions = list(active_acc.get("positions", {}).keys())
    for symbol in open_positions:
        try:
            curr_price = fetch_current_price(symbol)
            if curr_price is None:
                continue
                
            # Check if coin was manually sold in Binance (for real trading mode)
            if check_manual_sells and active_acc.get("mode") == "real" and real_balances is not None:
                base_asset = symbol.replace("USDT", "").replace("/", "").upper()
                actual_bal_info = real_balances.get(base_asset, {"free": 0.0, "locked": 0.0})
                actual_bal = actual_bal_info.get("free", 0.0) + actual_bal_info.get("locked", 0.0)
                position = active_acc["positions"][symbol]
                expected_size = position.get("remainingSize", position["size"])
                
                # If balance is less than 5% of expected size, it means it has been manually sold.
                if actual_bal < expected_size * 0.05:
                    db.add_log(f"[External Sync] {symbol} was manually sold or has no balance on Binance (Expected: {expected_size:.6f}, Found: {actual_bal:.6f}). Auto-closing position in bot.")
                    exit_position(symbol, curr_price, "EXTERNAL_SELL", "Sold manually outside the bot", skip_exchange=True)
                    # Re-read account state since we closed the position
                    active_acc = db.get_active_account()
                    continue

            position = active_acc["positions"][symbol]
            entry_price = position["buyPrice"]
            size = position["size"]
            
            # Check Time Stop (Max 12 Hours for 15m Trend Trading)
            entry_time_str = position.get("entryTime")
            if entry_time_str:
                try:
                    entry_time = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S")
                    elapsed_seconds = (datetime.now() - entry_time).total_seconds()
                    if elapsed_seconds >= 43200:  # 12 hours (48 bars on 15m)
                        db.add_log(f"[Time Trigger] Max duration (12 hours) reached for {symbol}. Closing position.")
                        exit_position(symbol, curr_price, "TIME_STOP_HIT", "Trade duration exceeded 12 hours")
                        order_executed = True
                        active_acc = db.get_active_account()
                        continue
                except Exception as ex:
                    db.add_log(f"[Time Check Error] Could not parse entry time for {symbol}: {ex}")

            stop_loss = position.get("stopLoss", 0)
            targets = position.get("targets", [])
            if targets:
                for idx, target in enumerate(targets):
                    if target["hit"]:
                        continue
                    if curr_price >= target["price"]:
                        sell_pct = target["sellPct"]
                        sell_qty = size * (sell_pct / 100)
                        
                        # 1. Execute live market sell order on exchange
                        mode = active_acc.get("mode", "paper")
                        
                        # Check Binance Spot minimum notional limit (5.0 USDT) to prevent NOTIONAL Filter failure
                        min_notional = 5.0
                        notional_value = sell_qty * curr_price
                        
                        if mode == "real":
                            remaining_qty = position.get("remainingSize", size)
                            remaining_notional = remaining_qty * curr_price
                            
                            if notional_value < min_notional:
                                if remaining_notional >= min_notional:
                                    db.add_log(f"[Notional Adjust] Target sell value for {symbol} is too small (${notional_value:.2f} < ${min_notional:.2f}). Adjusting to sell entire remaining size ({remaining_qty:.6f} {symbol}, value: ${remaining_notional:.2f}).")
                                    sell_qty = remaining_qty
                                else:
                                    db.add_log(f"[Notional Dust] Remaining position value for {symbol} is too small to trade on Binance (${remaining_notional:.2f} < ${min_notional:.2f}). Cleaning up locally.")
                                    exit_position(symbol, curr_price, "DUST_CLEANUP", "Value below exchange minimum notional", skip_exchange=True)
                                    order_executed = True
                                    break

                        db.add_log(f"[Multi-Target] {symbol} T{idx+1} triggered! Selling {sell_pct}% ({sell_qty:.6f} {symbol}) at {curr_price}...")
                        success = execute_exchange_order(symbol, "SELL", sell_qty, curr_price, mode, active_acc)
                        if not success:
                            db.add_log(f"[Multi-Target Error] Sell order failed on exchange for {symbol}. Skipped target processing.")
                            continue
                        order_executed = True
                            
                        # 2. Update DB state
                        def _update_target_hit(acc, actual_sell_qty):
                            if symbol not in acc.setdefault("positions", {}):
                                return
                            pos = acc["positions"][symbol]
                            pos_size = pos["size"]
                            
                            remaining = pos.get("remainingSize", pos_size) - actual_sell_qty
                            pos["remainingSize"] = max(0, remaining)
                            
                            pct_sold = (actual_sell_qty / pos_size) * 100
                            pos["allocatedCapital"] = round(pos.get("allocatedCapital", 0.0) * (1 - pct_sold / 100), 4)
                            
                            if acc.get("mode") != "real":
                                positions = acc.get("positions", {})
                                in_play = sum(p.get("allocatedCapital", 0.0) for p in positions.values())
                                acc["balance"] = round(acc.get("allocatedCapital", 500.0) - in_play, 2)
                            
                            if "targets" in pos and len(pos["targets"]) > idx:
                                pos["targets"][idx]["hit"] = True
                            
                            fee_rate = 0.001
                            gross_proceeds = actual_sell_qty * curr_price
                            buy_cost = actual_sell_qty * entry_price
                            fees_paid = round((buy_cost + gross_proceeds) * fee_rate, 4)
                            pnl_usd = round(gross_proceeds - buy_cost - fees_paid, 4)
                            pnl_pct = round(((curr_price - entry_price) / entry_price) * 100, 2)
                            
                            if acc.get("mode") != "real":
                                acc["totalBalance"] = round(acc.get("totalBalance", 1000.0) + pnl_usd, 2)
                            
                            journal = acc.setdefault("journal", {
                                "startingBalance": 1000.0,
                                "currentBalance": 1000.0,
                                "totalTrades": 0,
                                "winningTrades": 0,
                                "losingTrades": 0,
                                "totalPnL": 0.0
                            })
                            journal["totalTrades"] += 1
                            journal["totalPnL"] = round(journal["totalPnL"] + pnl_usd, 4)
                            if pnl_usd > 0:
                                journal["winningTrades"] += 1
                                
                            partial_log = {
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "accountName": acc["name"],
                                "mode": acc.get("mode", "paper"),
                                "coin": symbol,
                                "action": "PARTIAL_SELL",
                                "strategy": pos["strategy"],
                                "price": curr_price,
                                "size": actual_sell_qty,
                                "total": round(gross_proceeds, 2),
                                "fees": fees_paid,
                                "pnl_pct": pnl_pct,
                                "pnl_usd": pnl_usd,
                                "reason": f"TARGET_T{idx+1}_{target['price']}"
                            }
                            acc.setdefault("history", []).append(partial_log)
                            sheets.log_trade_to_sheets_async(partial_log)
                            
                            if idx == 0 and not pos.get("breakevenActivated"):
                                pos["stopLoss"] = entry_price
                                pos["breakevenActivated"] = True
                                db.add_log(f"[Breakeven] {symbol} SL → Breakeven ({entry_price:.4f})")
                                
                            if pos["remainingSize"] <= 0.00001:
                                db.add_log(f"[Multi-Target] {symbol} ALL targets hit. Fully closed.")
                                if symbol in acc.get("positions", {}):
                                    del acc["positions"][symbol]
                                    
                        db.update_active_account(lambda acc: _update_target_hit(acc, sell_qty))
                        active_acc = db.get_active_account()
                        if symbol not in active_acc.get("positions", {}):
                            break
                if symbol not in active_acc.get("positions", {}):
                    continue
            if curr_price <= stop_loss:
                db.add_log(f"[Risk Trigger] SL hit for {symbol} at {curr_price}")
                exit_position(symbol, curr_price, "STOP_LOSS_HIT", f"Stop Loss of {stop_loss} hit")
                order_executed = True
                active_acc = db.get_active_account()
        except Exception as e:
            db.add_log(f"[Risk Monitor Error] Error monitoring position for {symbol}: {e}")
            
    return order_executed

def run_scan_tick():
    state = db.get()
    trading_active = state.get("tradingActive", False)
    active_acc = db.get_active_account()
    if not active_acc:
        return
        
    # Check open positions risk instantly
    order_executed = run_risk_monitor(check_manual_sells=True)
    
    # Reload account state
    active_acc = db.get_active_account()
    if not active_acc:
        return
        
    real_balances = None
            
    # ── BINANCE BALANCE SYNC (Real mode) ─────────────────────────────────────
    # This is the SINGLE SOURCE OF TRUTH for real mode balances.
    # We always sync at the end of every tick — regardless of whether any order
    # was executed. This ensures freed USDT from partial sells immediately shows
    # up as available trading capital on the next scan without any internal math.
    if active_acc.get("mode") == "real":
        api_key = active_acc.get("apiKey", "")
        api_secret = active_acc.get("apiSecret", "")
        if api_key and api_secret:
            # Re-fetch balances after any order execution to get the latest state
            if order_executed or real_balances is None:
                real_balances = fetch_binance_balances(api_key, api_secret)
            
            if real_balances is not None:
                # Free USDT = what's available to trade right now
                usdt_info = real_balances.get("USDT", {"free": 0.0, "locked": 0.0})
                free_usdt = round(usdt_info.get("free", 0.0), 2)
                
                # Total NAV = USDT + value of all held coins (fetched from Binance prices)
                all_prices = fetch_all_binance_prices()
                total_nav = free_usdt  # start with free USDT
                for asset, bal_info in real_balances.items():
                    if asset == "USDT":
                        continue
                    qty = bal_info.get("free", 0.0) + bal_info.get("locked", 0.0)
                    if qty <= 0.0:
                        continue
                    pair = f"{asset}USDT"
                    if pair in all_prices:
                        total_nav += qty * all_prices[pair]
                
                # Compute in-play value from open bot positions using current prices
                active_acc = db.get_active_account()
                positions_value = 0.0
                for sym, pos in active_acc.get("positions", {}).items():
                    p_price = all_prices.get(sym) or fetch_current_price(sym)
                    if p_price:
                        sz = pos.get("remainingSize", pos["size"])
                        positions_value += sz * p_price
                
                # Fallback: if NAV is implausibly low, use free_usdt + positions_value
                if total_nav < free_usdt:
                    total_nav = free_usdt + positions_value
                
                db.update_real_balances(free_usdt, round(total_nav, 2), positions_value)
                active_acc = db.get_active_account()
                db.add_log(
                    f"[Balance Sync] Total: ${total_nav:.2f} | "
                    f"Free USDT: ${free_usdt:.2f} | "
                    f"In-Play: ${positions_value:.2f}"
                )


    if not trading_active:
        db.add_log("[Scan Tick] Trading is PAUSED. Skipping new trade entries research.")
        return

    # Fetch active watchlist from GLOBAL pool (shared across all accounts)
    active_wl_name = active_acc.get("activeWatchlistName", "Default List")
    global_wls = state.get("globalWatchlists", {})
    watchlist = global_wls.get(active_wl_name, [])
    db.add_log(f"[Scan Tick] Account: {active_acc['name']} | Watchlist: '{active_wl_name}' ({len(watchlist)} coins)")

    max_trades = active_acc.get("maxConcurrentTrades", 5)
    
    # Count active "full" positions only — positions that have been mostly sold (remainingSize < 30% of original)
    # are treated as winding down and don't block new entries
    def _count_active_positions(positions):
        count = 0
        for pos in positions.values():
            remaining = pos.get("remainingSize", pos["size"])
            original = pos["size"]
            if original > 0 and (remaining / original) >= 0.30:
                count += 1
        return count
    
    current_trades_count = _count_active_positions(active_acc.get("positions", {}))
    if current_trades_count >= max_trades:
        db.add_log(f"[Scan Tick] Max concurrent trades ({current_trades_count}/{max_trades}) reached. Skipping scanning for new signals.")
        return
    for symbol in watchlist:
        if _count_active_positions(active_acc.get("positions", {})) >= max_trades:
            db.add_log("[Scan Tick] Max concurrent trades reached mid-scan. Aborting search.")
            break
        if symbol in active_acc.get("positions", {}):

            continue
        db.add_log(f"[Research] Scanning {symbol} on 15m candlestick history...")
        try:
            highs, lows, closes = fetch_candles(symbol)
            if not closes or len(closes) < 35:
                db.add_log(f"[Research] {symbol}: Insufficient candles history. Skipping.")
                continue
            signals = strategies.evaluate_signals(highs, lows, closes)
            db.update_strategy_signals(symbol, signals)
            curr_price = closes[-1]
            sig_status = ", ".join([f"{strat}: {sig}" for strat, sig in signals.items()])
            db.add_log(f"[Research] {symbol} Price: {curr_price} | Evaluations: [{sig_status}]")
            
            triggered = False
            # Only trade the best strategy (EMA_MACD_Crossover) as verified by historical backtesting (60.0% win rate, 1:2 RR)
            best_strategy = "EMA_MACD_Crossover"
            signal = signals.get(best_strategy, "HOLD")
            if signal == "BUY":
                db.add_log(f"[Signal Triggered] BUY signal on {symbol} via '{best_strategy}' at price {curr_price}")
                enter_position(symbol, curr_price, best_strategy)
                triggered = True
        except Exception as e:
            db.add_log(f"[Research Error] Error scanning coin {symbol}: {e}")

def fetch_current_price(symbol):
    binance_url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    data = _request_with_retry(binance_url)
    if data and "price" in data:
        return float(data["price"])
    coin = symbol.replace("USDT", "").upper()
    coinbase_url = f"https://api.coinbase.com/v2/prices/{coin}-USD/spot"
    data = _request_with_retry(coinbase_url)
    if data and "data" in data and "amount" in data["data"]:
        try:
            return float(data["data"]["amount"])
        except:
            pass
    db.add_log(f"[Backend Error] Unable to fetch price for {symbol}.")
    return None

def fetch_candles(symbol, timeframe="15m", limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
    data = _request_with_retry(url)
    if not data:
        return [], [], []
    highs = [float(item[2]) for item in data]
    lows = [float(item[3]) for item in data]
    closes = [float(item[4]) for item in data]
    return highs, lows, closes

def enter_position(symbol, price, strategy_name):
    def _update_db(acc):
        max_trades = acc.get("maxConcurrentTrades", 5)
        allocated_cap = acc.get("allocatedCapital", 500.0)
        mode = acc.get("mode", "paper")
        positions = acc.get("positions", {})
        
        active_slots = len(positions)
        slots_left = max_trades - active_slots
        
        if mode == "real":
            # Real mode: free_capital = Binance free USDT (synced every tick)
            free_capital = acc.get("balance", 0.0)
            
            # Minimum to trade: $10 (covers Binance minimum notional limit + buffer)
            if free_capital < 10.0:
                db.add_log(f"[Order Blocked] Insufficient free USDT (${free_capital:.2f}) for {symbol}. Need at least $10.")
                return
            
            if slots_left <= 1:
                # Last slot gets 100% of the remaining free capital
                trade_capital = free_capital
            else:
                # Early slots get free_capital / slots_left
                trade_capital = round(free_capital / slots_left, 2)
                
            trade_capital = round(trade_capital * 0.98, 2) # 2% buffer for fees
            
            if trade_capital < 10.0:
                trade_capital = round(free_capital * 0.98, 2)
                
            if trade_capital < 10.0:
                db.add_log(f"[Order Blocked] Calculated size (${trade_capital:.2f}) is below Binance minimum $10 for {symbol}.")
                return
        else:
            in_play = sum(pos.get("allocatedCapital", 0.0) for pos in positions.values())
            free_capital = round(allocated_cap - in_play, 2)
            
            if slots_left <= 1:
                # Last slot gets 100% of the remaining free capital
                trade_capital = free_capital
            else:
                # Early slots get free_capital / slots_left
                trade_capital = round(free_capital / slots_left, 2)
                
            if trade_capital > free_capital:
                trade_capital = free_capital
                
            if trade_capital < 10.0:
                trade_capital = free_capital
                
            if trade_capital < 10.0:
                db.add_log(f"[Order Blocked] Insufficient free trading capital (${free_capital:.2f}) to allocate size for {symbol} (min $10).")
                return
            
        success = execute_exchange_order(symbol, "BUY", trade_capital / price, price, mode, acc)
        if not success:
            db.add_log(f"[Order Blocked] Exchange order failed for {symbol}.")
            return
        size = trade_capital / price
        
        # Define Risk Management levels
        if strategy_name == "EMA_MACD_Crossover":
            stop_loss = round(price * 0.990, 6)   # -1.0% SL
            tp1 = round(price * 1.020, 6)          # +2.0% TP
            targets_to_save = [
                {"price": tp1, "sellPct": 100, "hit": False}
            ]
        else:
            default_sl_pct = 0.005
            stop_loss = round(price * (1 - default_sl_pct), 6)
            tp1 = round(price * 1.010, 6)
            tp2 = round(price * 1.015, 6)
            tp3 = round(price * 1.025, 6)
            targets_to_save = [
                {"price": tp1, "sellPct": 50, "hit": False},
                {"price": tp2, "sellPct": 25, "hit": False},
                {"price": tp3, "sellPct": 25, "hit": False},
            ]
            
        if strategy_name != "EMA_MACD_Crossover":
            try:
                highs_st, lows_st, closes_st = fetch_candles(symbol, timeframe="15m", limit=60)
                if closes_st and len(closes_st) >= 20:
                    st_vals, st_dirs = strategies.calculate_supertrend_local(highs_st, lows_st, closes_st, period=10, multiplier=3.0)
                    if st_vals and len(st_vals) > 0 and st_dirs and len(st_dirs) > 0:
                        curr_st_val = st_vals[-1]
                        curr_st_dir = st_dirs[-1]
                        if curr_st_dir == 1 and curr_st_val < price:
                            try:
                                atr_vals = indicators.calculate_atr(highs_st, lows_st, closes_st, period=14)
                                if atr_vals and len(atr_vals) > 0:
                                      curr_atr = atr_vals[-1]
                                      buffer = curr_atr * 0.5
                                      dynamic_sl = round(curr_st_val - buffer, 6)
                                else:
                                      dynamic_sl = round(curr_st_val * 0.998, 6)
                            except:
                                dynamic_sl = round(curr_st_val * 0.998, 6)
                            dynamic_risk = price - dynamic_sl
                            max_risk = price * 0.02
                            if dynamic_risk > max_risk:
                                dynamic_sl = round(price - max_risk, 6)
                                dynamic_risk = max_risk
                            if dynamic_risk > 0:
                                stop_loss = dynamic_sl
                                tp1 = round(price + (dynamic_risk * 1.0), 6)
                                tp2 = round(price + (dynamic_risk * 1.5), 6)
                                tp3 = round(price + (dynamic_risk * 2.5), 6)
                                targets_to_save = [
                                    {"price": tp1, "sellPct": 50, "hit": False},
                                    {"price": tp2, "sellPct": 25, "hit": False},
                                    {"price": tp3, "sellPct": 25, "hit": False},
                                ]
            except Exception as e:
                db.add_log(f"[Dynamic SL] Could not calculate for {symbol}: {e} — Using fixed SL/TP")
                
        acc["positions"][symbol] = {
            "symbol": symbol,
            "buyPrice": price,
            "size": size,
            "entryTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "strategy": strategy_name,
            "stopLoss": stop_loss,
            "takeProfit": tp1,
            "allocatedCapital": trade_capital,
            "targets": targets_to_save,
            "breakevenActivated": False,
            "remainingSize": size
        }
        if mode == "real":
            acc["balance"] = round(max(0.0, acc.get("balance", 0.0) - trade_capital), 2)
        else:
            positions = acc.get("positions", {})
            in_play = sum(pos.get("allocatedCapital", 0.0) for pos in positions.values())
            acc["balance"] = round(allocated_cap - in_play, 2)
        trade_log = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "accountName": acc["name"],
            "mode": mode,
            "coin": symbol,
            "action": "BUY",
            "strategy": strategy_name,
            "price": price,
            "size": size,
            "total": trade_capital,
            "reason": f"Strategy Entry ({strategy_name})"
        }
        sheets.log_trade_to_sheets_async(trade_log)
        db.add_log(f"[Position Opened] {symbol} | Price: {price} | SL: {stop_loss} | TP1: {tp1}")
    db.update_active_account(_update_db)

def exit_position(symbol, price, reason_code, description="", skip_exchange=False):
    def _update_db(acc):
        if symbol not in acc.get("positions", {}):
            return
        pos = acc["positions"][symbol]
        buy_price = pos["buyPrice"]
        size = pos.get("remainingSize", pos["size"])
        strategy = pos["strategy"]
        trade_capital = pos["allocatedCapital"]
        mode = acc["mode"]
        if size <= 0:
            if symbol in acc.get("positions", {}):
                del acc["positions"][symbol]
            return
        
        # Check Binance Spot minimum notional limit (5.0 USDT) for stop losses/exits
        min_notional = 5.0
        notional_value = size * price
        
        # Use a local variable to avoid Python scoping issue with inner function assignment
        _skip = skip_exchange
        if mode == "real" and notional_value < min_notional and not _skip:
            db.add_log(f"[Notional Dust SL] Position value for {symbol} is too small to trade on Binance (${notional_value:.2f} < ${min_notional:.2f}). Cleaning up locally.")
            _skip = True
            
        if not _skip:
            success = execute_exchange_order(symbol, "SELL", size, price, mode, acc)
            if not success:
                db.add_log(f"[Order Blocked] Sell order failed on exchange for {symbol}.")
                return
        else:
            db.add_log(f"[Cleanup] Skipping exchange order execution for {symbol} (already sold externally/dust).")

        pnl_usd = round((price - buy_price) * size, 2)
        pnl_pct = round(((price - buy_price) / buy_price) * 100, 2)
        
        if symbol in acc.get("positions", {}):
            del acc["positions"][symbol]
            
        # PnL calculation with fees (0.1% Binance fee on both sides)
        fee_rate = 0.001
        buy_cost = size * buy_price
        gross_proceeds = size * price
        fees_paid = round((buy_cost + gross_proceeds) * fee_rate, 4)
        pnl_usd = round(gross_proceeds - buy_cost - fees_paid, 4)
        pnl_pct = round(((price - buy_price) / buy_price) * 100, 2)
        
        if mode == "real":
            # Real mode: DO NOT update balance/totalBalance here.
            # Binance sync at end of every tick will set the authoritative values.
            # allocatedCapital stays = totalBalance for slot-size calculations.
            pass
        else:
            acc["totalBalance"] = round(acc.get("totalBalance", 1000.0) + pnl_usd, 2)
            positions = acc.get("positions", {})
            in_play = sum(pos.get("allocatedCapital", 0.0) for pos in positions.values())
            acc["balance"] = round(acc.get("allocatedCapital", 500.0) - in_play, 2)
        trade_log = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "accountName": acc["name"],
            "mode": mode,
            "coin": symbol,
            "action": "SELL",
            "strategy": strategy,
            "price": price,
            "size": size,
            "total": round(gross_proceeds, 2),
            "fees": fees_paid,
            "pnl_pct": pnl_pct,
            "pnl_usd": pnl_usd,
            "reason": reason_code
        }
        acc["history"].append(trade_log)
        journal = acc["journal"]
        journal["totalTrades"] += 1
        journal["totalPnL"] = round(journal["totalPnL"] + pnl_usd, 4)
        if pnl_usd > 0:
            journal["winningTrades"] += 1
        else:
            journal["losingTrades"] += 1
        if mode != "real":
            journal["currentBalance"] = acc["totalBalance"]
        sheets.log_trade_to_sheets_async(trade_log)
        db.add_log(f"[Position Closed] {symbol} | Exit: ${price} | Gross: ${gross_proceeds:.2f} | Fees: ${fees_paid:.4f} | Net PnL: ${pnl_usd} ({pnl_pct}%) | Reason: {reason_code}")
    db.update_active_account(_update_db)

def fetch_all_holdings(api_key, api_secret):
    """Fetches all Binance account balances with USD values for the portfolio panel."""
    balances = fetch_binance_balances(api_key, api_secret)
    if balances is None:
        return {"error": "Failed to fetch balances from Binance", "holdings": []}
    
    all_prices = fetch_all_binance_prices()
    holdings = []
    
    for asset, bal_info in balances.items():
        free = bal_info.get("free", 0.0)
        locked = bal_info.get("locked", 0.0)
        total_qty = free + locked
        if total_qty < 0.000001:
            continue
        
        if asset == "USDT":
            usd_value = total_qty
            price = 1.0
        else:
            pair = f"{asset}USDT"
            price = all_prices.get(pair, 0.0)
            usd_value = total_qty * price if price > 0 else 0.0
        
        holdings.append({
            "asset": asset,
            "free": round(free, 8),
            "locked": round(locked, 8),
            "total": round(total_qty, 8),
            "price": price,
            "usdValue": round(usd_value, 4),
            "isUsdt": asset == "USDT"
        })
    
    # Sort: USDT first, then by USD value descending
    holdings.sort(key=lambda x: (0 if x["isUsdt"] else 1, -x["usdValue"]))
    
    total_usd = sum(h["usdValue"] for h in holdings)
    return {
        "holdings": holdings,
        "totalUsd": round(total_usd, 2),
        "count": len(holdings)
    }

def manual_sell_holding(account, asset, mode="pct", value=100.0):
    """Manually sells a percentage or USD value of a held asset at market price."""
    if asset == "USDT":
        return {"success": False, "error": "Cannot sell USDT — it is your base currency."}
    
    api_key = account.get("apiKey", "")
    api_secret = account.get("apiSecret", "")
    
    # Get current balance
    balances = fetch_binance_balances(api_key, api_secret)
    if balances is None:
        return {"success": False, "error": "Could not fetch live balance from Binance."}
    
    bal_info = balances.get(asset, {"free": 0.0, "locked": 0.0})
    free_qty = bal_info.get("free", 0.0)
    
    if free_qty <= 0:
        return {"success": False, "error": f"No free {asset} balance available to sell (may be locked in open order)."}
    
    symbol = f"{asset}USDT"
    
    # Get current price
    curr_price = fetch_current_price(symbol)
    if curr_price is None:
        return {"success": False, "error": f"Could not fetch current price for {symbol}."}
        
    if mode == "pct":
        sell_qty = free_qty * (value / 100.0)
        log_desc = f"{value:.1f}%"
    else:
        # USD value mode
        sell_qty = value / curr_price
        log_desc = f"${value:.2f}"
        
    if sell_qty > free_qty:
        sell_qty = free_qty
    
    notional = sell_qty * curr_price
    if notional < 5.0:
        return {
            "success": False,
            "error": f"Sell value ${notional:.2f} is below Binance minimum $5. "
                     f"You have {free_qty:.6f} {asset} worth ${free_qty * curr_price:.2f}."
        }
    
    db.add_log(f"[Manual Sell] Selling {log_desc} of {asset} ({sell_qty:.6f} {asset}) at ${curr_price} ≈ ${notional:.2f}...")
    success = execute_exchange_order(symbol, "SELL", sell_qty, curr_price, "real", account)
    
    if success:
        db.add_log(f"[Manual Sell] ✅ {asset} sell executed successfully.")
        return {
            "success": True,
            "asset": asset,
            "qty": round(sell_qty, 6),
            "price": curr_price,
            "usdValue": round(notional, 2),
            "message": f"Sold {sell_qty:.6f} {asset} for ≈ ${notional:.2f} USDT"
        }
    else:
        return {"success": False, "error": f"Exchange order failed for {asset}. Check logs for details."}

def force_close_position(symbol):
    price = fetch_current_price(symbol)
    if price is not None:
        exit_position(symbol, price, "MANUAL_CLOSE", "Manually closed via dashboard button")
        return True
    return False

def force_close_all_positions():
    active_acc = db.get_active_account()
    if not active_acc:
        return
    open_symbols = list(active_acc.get("positions", {}).keys())
    for symbol in open_symbols:
        force_close_position(symbol)

def execute_exchange_order(symbol, side, quantity, price, mode, account):
    if mode == "paper":
        return True
    api_key = account.get("apiKey", "")
    api_secret = account.get("apiSecret", "")
    if not api_key or not api_secret:
        db.add_log(f"[Exchange Error] Cannot execute live {side} order for {symbol}: API Credentials missing.")
        return False
    try:
        import ccxt
    except ImportError:
        db.add_log(f"[Dependency Error] CCXT library is not installed. Please run: pip install ccxt")
        return False
    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        exchange.load_markets()
        
        # Convert symbol to CCXT unified format (e.g. BTCUSDT -> BTC/USDT)
        ccxt_symbol = symbol
        if '/' not in symbol and symbol.endswith('USDT'):
            ccxt_symbol = symbol[:-4] + '/USDT'
            
        precise_qty = quantity
        
        # Fee and balance adjustment for SELL orders
        if side == "SELL":
            try:
                base_asset = symbol.replace("USDT", "")
                if '/' in symbol:
                    base_asset = symbol.split('/')[0]
                
                balance_info = exchange.fetch_balance()
                free_balance = float(balance_info.get(base_asset, {}).get('free', 0.0))
                
                if free_balance < quantity:
                    db.add_log(f"[Exchange API] Adjusting sell quantity from {quantity:.6f} to available balance {free_balance:.6f} due to fees.")
                    precise_qty = free_balance
            except Exception as bal_err:
                db.add_log(f"[Exchange API Warning] Could not check free balance: {bal_err}. Proceeding with original quantity.")
        
        # Format the quantity to correct step-size and decimal limits for Binance Spot
        precise_qty = float(exchange.amount_to_precision(ccxt_symbol, precise_qty))
        if precise_qty <= 0:
            if side == "SELL":
                db.add_log(f"[Exchange Order] Live {symbol} balance is 0. Resolving position cleanup.")
                return True
            else:
                db.add_log(f"[Exchange Order Error] Rounded quantity is {precise_qty} (original: {quantity}) which is invalid for {symbol}.")
                return False
        
        # Check minimum notional value ($5 USDT) after step-size rounding
        # If below minimum for SELL, treat as dust — clean up locally without exchange order
        notional = precise_qty * price
        if side == "SELL" and notional < 5.0:
            db.add_log(f"[Exchange Order] {symbol} sell value ${notional:.2f} is below Binance $5 minimum notional after rounding. Treating as dust — cleaning up locally.")
            return True
            
        db.add_log(f"[Exchange API] Executing LIVE Binance Market {side} order for {precise_qty} {symbol} (original: {quantity:.6f})...")
        if side == "BUY":
            order = exchange.create_market_buy_order(ccxt_symbol, precise_qty)
        else:
            order = exchange.create_market_sell_order(ccxt_symbol, precise_qty)
        order_id = order.get('id', 'Unknown')
        db.add_log(f"[Exchange Order] Live {side} order executed successfully! Order ID: {order_id}")
        return True
    except Exception as e:
        db.add_log(f"[Exchange API Error] Failed to place live order on Binance: {e}")
        return False