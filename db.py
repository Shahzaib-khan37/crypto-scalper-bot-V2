import os
import json
import threading
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db.json')
db_lock = threading.Lock()

# Global in-memory logs list (stops heavy disk writes for simple log events)
system_logs = []
strategy_signals = {}

def update_strategy_signals(symbol, signals):
    """Updates the in-memory strategy signals for a coin."""
    global strategy_signals
    strategy_signals[symbol] = signals


def add_log(message):
    """Adds a log line with timestamp to the system logs memory and prints to console."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    system_logs.append(log_line)
    # Keep only the last 60 logs
    if len(system_logs) > 60:
        system_logs.pop(0)

# ── DEFAULT DATABASE SCHEMA ─────────────────────────────────────────────────
# Watchlists are GLOBAL — shared across all accounts.
# Each account only stores 'activeWatchlistName' (a reference to globalWatchlists).
DEFAULT_DB = {
    "activeAccountName": "Default Paper Account",
    "tradingActive": False,
    "googleSheetsWebhookUrl": "",
    "globalWatchlists": {
        "Default List": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT"]
    },
    "accounts": {
        "Default Paper Account": {
            "name": "Default Paper Account",
            "mode": "paper",
            "apiKey": "",
            "apiSecret": "",
            "balance": 1000.0,
            "totalBalance": 1000.0,
            "allocatedCapital": 500.0,
            "maxConcurrentTrades": 5,
            "activeWatchlistName": "Default List",
            "positions": {},
            "history": [],
            "journal": {
                "startingBalance": 1000.0,
                "currentBalance": 1000.0,
                "totalTrades": 0,
                "winningTrades": 0,
                "losingTrades": 0,
                "totalPnL": 0.0
            }
        }
    }
}

_db_state = None

def init():
    global _db_state
    with db_lock:
        if os.path.exists(DB_PATH):
            try:
                with open(DB_PATH, 'r', encoding='utf-8') as f:
                    _db_state = json.load(f)
                add_log(f"Database loaded successfully from {DB_PATH}")

                if "activeAccountName" not in _db_state or "accounts" not in _db_state:
                    raise ValueError("Malformed database structure")

                migrated = False

                # ── MIGRATION 1: Per-account watchlists → Global watchlists ─────────
                # Collect all per-account watchlists and merge into globalWatchlists.
                if "globalWatchlists" not in _db_state:
                    _db_state["globalWatchlists"] = {
                        "Default List": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT"]
                    }
                    for acc_name, acc in _db_state["accounts"].items():
                        if "watchlists" in acc:
                            for wl_name, wl_coins in acc["watchlists"].items():
                                if wl_name not in _db_state["globalWatchlists"]:
                                    _db_state["globalWatchlists"][wl_name] = wl_coins
                    add_log("[Migration] Watchlists consolidated from per-account to global shared pool.")
                    migrated = True

                # ── MIGRATION 2: Clean up per-account watchlists leftover ──────────
                for acc_name, acc in _db_state["accounts"].items():
                    if "watchlists" in acc:
                        for wl_name, wl_coins in acc["watchlists"].items():
                            if wl_name not in _db_state["globalWatchlists"]:
                                _db_state["globalWatchlists"][wl_name] = wl_coins
                        del acc["watchlists"]
                        migrated = True

                    # Validate activeWatchlistName — if it points to a missing watchlist, reset it
                    active_wl = acc.get("activeWatchlistName", "Default List")
                    if active_wl not in _db_state["globalWatchlists"]:
                        acc["activeWatchlistName"] = list(_db_state["globalWatchlists"].keys())[0]
                        migrated = True

                    # ── MIGRATION 3: totalBalance field ───────────────────────────
                    if "totalBalance" not in acc:
                        positions = acc.get("positions", {})
                        in_play = sum(pos.get("allocatedCapital", 0.0) for pos in positions.values())
                        acc["totalBalance"] = round(acc.get("balance", 1000.0) + in_play, 2)
                        migrated = True

                if migrated:
                    add_log("[Migration] Database schema updated successfully.")
                    _save_unlocked()

            except Exception as e:
                add_log(f"Failed to load db.json ({e}). Re-initializing default database.")
                _db_state = json.loads(json.dumps(DEFAULT_DB))
                _save_unlocked()
        else:
            add_log(f"No existing db.json found. Creating default database at {DB_PATH}")
            _db_state = json.loads(json.dumps(DEFAULT_DB))
            _save_unlocked()

def _save_unlocked():
    try:
        with open(DB_PATH, 'w', encoding='utf-8') as f:
            json.dump(_db_state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Failed to write db.json: {e}")

def save():
    with db_lock:
        _save_unlocked()

def get():
    with db_lock:
        return _db_state

def get_safe_state():
    with db_lock:
        if not _db_state:
            return {}

        safe_accounts = {}
        for name, acc in _db_state.get("accounts", {}).items():
            positions = acc.get("positions", {})

            if acc.get("mode") == "real":
                current_balance = round(acc.get("balance", 0.0), 2)
            else:
                in_play = sum(pos.get("allocatedCapital", 0.0) for pos in positions.values())
                current_balance = round(acc.get("allocatedCapital", 500.0) - in_play, 2)

            safe_accounts[name] = {
                "name": acc.get("name"),
                "mode": acc.get("mode"),
                "balance": current_balance,
                "totalBalance": acc.get("totalBalance", 1000.0),
                "allocatedCapital": acc.get("allocatedCapital", 500.0),
                "maxConcurrentTrades": acc.get("maxConcurrentTrades", 5),
                "activeWatchlistName": acc.get("activeWatchlistName", "Default List"),
                "positions": acc.get("positions", {}),
                "history": acc.get("history", []),
                "journal": acc.get("journal", {}),
                "hasCredentials": bool(acc.get("apiKey") and acc.get("apiSecret"))
            }

        return {
            "activeAccountName": _db_state.get("activeAccountName"),
            "tradingActive": _db_state.get("tradingActive", False),
            "googleSheetsWebhookUrl": _db_state.get("googleSheetsWebhookUrl", ""),
            "globalWatchlists": _db_state.get("globalWatchlists", {"Default List": []}),
            "accounts": safe_accounts,
            "logs": system_logs,
            "strategySignals": strategy_signals
        }

def get_active_account():
    with db_lock:
        if not _db_state:
            return None
        active_name = _db_state.get("activeAccountName")
        return _db_state.get("accounts", {}).get(active_name)

def update_active_account(update_fn):
    with db_lock:
        if not _db_state:
            return
        active_name = _db_state.get("activeAccountName")
        active = _db_state.get("accounts", {}).get(active_name)
        if active:
            update_fn(active)
            _save_unlocked()

def add_account(name, mode, api_key='', api_secret='', initial_balance=1000.0):
    global _db_state
    with db_lock:
        if name in _db_state["accounts"]:
            raise ValueError(f"Account '{name}' already exists.")

        try:
            init_bal = max(0.0, float(initial_balance))
        except ValueError:
            init_bal = 1000.0

        allocated = round(init_bal * 0.5, 2)

        # New account defaults to the first available global watchlist
        global_wls = _db_state.get("globalWatchlists", {"Default List": []})
        first_wl = list(global_wls.keys())[0] if global_wls else "Default List"

        _db_state["accounts"][name] = {
            "name": name,
            "mode": mode or "paper",
            "apiKey": api_key or "",
            "apiSecret": api_secret or "",
            "totalBalance": init_bal,
            "allocatedCapital": allocated,
            "balance": allocated,
            "maxConcurrentTrades": 5,
            "activeWatchlistName": first_wl,
            "positions": {},
            "history": [],
            "journal": {
                "startingBalance": init_bal,
                "currentBalance": init_bal,
                "totalTrades": 0,
                "winningTrades": 0,
                "losingTrades": 0,
                "totalPnL": 0.0
            }
        }
        _save_unlocked()
    add_log(f"New account profile created: '{name}' ({mode.upper()}) | Initial Balance: ${init_bal:.2f}")
    return get_safe_state()

def delete_account(name):
    global _db_state
    with db_lock:
        if name not in _db_state["accounts"]:
            raise ValueError(f"Account '{name}' not found.")
        if name == _db_state["activeAccountName"]:
            raise ValueError("Cannot delete the active account. Switch to another account first.")
        if len(_db_state["accounts"]) <= 1:
            raise ValueError("Cannot delete the last remaining account.")

        del _db_state["accounts"][name]
        _save_unlocked()
    add_log(f"Account profile deleted: '{name}'")
    return get_safe_state()

def set_active_account(name):
    global _db_state
    with db_lock:
        if name not in _db_state["accounts"]:
            raise ValueError(f"Account '{name}' not found.")
        _db_state["activeAccountName"] = name
        # Always safety-pause when changing account
        _db_state["tradingActive"] = False
        _save_unlocked()
    add_log(f"Switched active account profile to '{name}'")
    return get_safe_state()

def set_trading_active(status):
    global _db_state
    with db_lock:
        _db_state["tradingActive"] = bool(status)
        _save_unlocked()
    add_log(f"Trading active set to {status}")
    return get_safe_state()

def update_real_balances(free_usdt, total_usdt, positions_value):
    def _update(acc):
        if acc.get("mode") == "real":
            acc["totalBalance"] = round(total_usdt, 2)
            acc["balance"] = round(free_usdt, 2)
            acc["allocatedCapital"] = round(total_usdt, 2)
    update_active_account(_update)

def update_settings(max_trades, allocated_capital, google_sheets_webhook_url=None, total_balance=None):
    global _db_state
    with db_lock:
        active_name = _db_state.get("activeAccountName")
        active = _db_state.get("accounts", {}).get(active_name)
        if active:
            active["maxConcurrentTrades"] = max(1, int(max_trades))

            alloc_cap = max(1.0, float(allocated_capital))

            if total_balance is not None and active.get("mode") == "paper":
                new_total = max(1.0, float(total_balance))
                active["totalBalance"] = new_total
                if alloc_cap > new_total:
                    alloc_cap = new_total

            active["allocatedCapital"] = alloc_cap

            positions = active.get("positions", {})
            in_play = sum(pos.get("allocatedCapital", 0.0) for pos in positions.values())
            active["balance"] = round(active["allocatedCapital"] - in_play, 2)

        if google_sheets_webhook_url is not None:
            _db_state["googleSheetsWebhookUrl"] = google_sheets_webhook_url
        _save_unlocked()
    add_log(f"Parameters updated: Max Trades={max_trades}, Capital={allocated_capital}" + (f", Total Balance={total_balance}" if total_balance is not None and active.get("mode") == "paper" else ""))
    return get_safe_state()


# ── GLOBAL WATCHLIST MANAGEMENT ──────────────────────────────────────────────
# All watchlists are stored under _db_state["globalWatchlists"].
# Accounts only store which watchlist they're currently using (activeWatchlistName).

def _global_wls():
    """Returns the global watchlists dict. Must be called while holding db_lock."""
    return _db_state.setdefault("globalWatchlists", {"Default List": []})

def create_watchlist(name):
    """Creates a new empty global watchlist and sets it as the active account's selection."""
    global _db_state
    formatted = name.strip()
    if not formatted:
        raise ValueError("Watchlist name cannot be empty")
    with db_lock:
        wls = _global_wls()
        if formatted in wls:
            raise ValueError(f"Watchlist '{formatted}' already exists.")
        wls[formatted] = []
        # Auto-select the new watchlist for the active account
        active_name = _db_state.get("activeAccountName")
        active = _db_state.get("accounts", {}).get(active_name)
        if active:
            active["activeWatchlistName"] = formatted
        _save_unlocked()
    add_log(f"[Watchlist] Created new global watchlist: '{formatted}'")
    return get_safe_state()

def delete_watchlist(name):
    """Deletes a global watchlist. All accounts using it are redirected to the first remaining one."""
    global _db_state
    formatted = name.strip()
    with db_lock:
        wls = _global_wls()
        if formatted not in wls:
            raise ValueError(f"Watchlist '{formatted}' not found.")
        if len(wls) <= 1:
            raise ValueError("Cannot delete the last remaining watchlist.")

        del wls[formatted]
        fallback = list(wls.keys())[0]

        # Redirect any account that was using the deleted watchlist
        for acc in _db_state.get("accounts", {}).values():
            if acc.get("activeWatchlistName") == formatted:
                acc["activeWatchlistName"] = fallback

        _save_unlocked()
    add_log(f"[Watchlist] Deleted global watchlist: '{formatted}'")
    return get_safe_state()

def rename_watchlist(old_name, new_name):
    """Renames a global watchlist. Updates all accounts that referenced the old name."""
    global _db_state
    old_f = old_name.strip()
    new_f = new_name.strip()
    if not old_f or not new_f:
        raise ValueError("Watchlist name cannot be empty")
    with db_lock:
        wls = _global_wls()
        if old_f not in wls:
            raise ValueError(f"Watchlist '{old_f}' not found.")
        if new_f in wls and new_f != old_f:
            raise ValueError(f"A watchlist named '{new_f}' already exists.")
        if old_f == new_f:
            return get_safe_state()

        # Rebuild dict to preserve insertion order with the new name in place
        new_wls = {}
        for k, v in wls.items():
            new_wls[new_f if k == old_f else k] = v
        _db_state["globalWatchlists"] = new_wls

        # Update all accounts that pointed to the old name
        for acc in _db_state.get("accounts", {}).values():
            if acc.get("activeWatchlistName") == old_f:
                acc["activeWatchlistName"] = new_f

        _save_unlocked()
    add_log(f"[Watchlist] Renamed '{old_f}' → '{new_f}'")
    return get_safe_state()

def select_watchlist(name):
    """Sets the currently selected watchlist for the active account."""
    global _db_state
    formatted = name.strip()
    with db_lock:
        wls = _global_wls()
        if formatted not in wls:
            raise ValueError(f"Watchlist '{formatted}' not found.")
        active_name = _db_state.get("activeAccountName")
        active = _db_state.get("accounts", {}).get(active_name)
        if active:
            active["activeWatchlistName"] = formatted
        _save_unlocked()
    add_log(f"[Watchlist] Active account switched to watchlist: '{formatted}'")
    return get_safe_state()

def add_to_watchlist(symbol):
    """Adds a coin to the active account's currently selected global watchlist."""
    formatted = symbol.strip().upper()
    if not formatted:
        return get_safe_state()

    with db_lock:
        wls = _global_wls()
        active_name = _db_state.get("activeAccountName")
        active = _db_state.get("accounts", {}).get(active_name)
        active_wl_name = active.get("activeWatchlistName", "Default List") if active else "Default List"

        if active_wl_name not in wls:
            wls[active_wl_name] = []
        if formatted not in wls[active_wl_name]:
            wls[active_wl_name].append(formatted)
            add_log(f"[Watchlist] Added {formatted} to '{active_wl_name}'")
        _save_unlocked()
    return get_safe_state()

def remove_from_watchlist(symbol):
    """Removes a coin from the active account's currently selected global watchlist."""
    formatted = symbol.strip().upper()
    with db_lock:
        wls = _global_wls()
        active_name = _db_state.get("activeAccountName")
        active = _db_state.get("accounts", {}).get(active_name)
        active_wl_name = active.get("activeWatchlistName", "Default List") if active else "Default List"

        if active_wl_name in wls:
            wls[active_wl_name] = [s for s in wls[active_wl_name] if s != formatted]
            add_log(f"[Watchlist] Removed {formatted} from '{active_wl_name}'")
        _save_unlocked()
    return get_safe_state()

# Auto-initialize database on import
init()
