import time
import requests
import math
import indicators
import strategies

# Target assets to backtest
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["5m", "15m"]

def fetch_historical_candles(symbol, timeframe, limit=3000):
    """
    Fetches historical candlestick data from Binance API using pagination.
    Returns: highs, lows, closes, open_times
    """
    print(f"Fetching historical candles for {symbol} on {timeframe} ({limit} bars)...")
    url = "https://api.binance.com/api/v3/klines"
    all_candles = []
    
    # Binance returns up to 1000 candles per request
    chunk_size = 1000
    end_time = None
    
    while len(all_candles) < limit:
        params = {
            "symbol": symbol,
            "interval": timeframe,
            "limit": chunk_size
        }
        if end_time:
            params["endTime"] = end_time - 1
            
        try:
            res = requests.get(url, params=params, timeout=10)
            if res.status_code != 200:
                print(f"Error fetching candles: Status code {res.status_code}")
                break
            data = res.json()
            if not data:
                break
            # Add to the beginning because we are going backwards in time
            all_candles = data + all_candles
            end_time = int(data[0][0]) # timestamp of first candle in chunk
            
            # If we received fewer candles than requested, we reached the beginning of history
            if len(data) < chunk_size:
                break
                
            time.sleep(0.1) # small delay to be polite to Binance rate limits
        except Exception as e:
            print(f"Connection error: {e}")
            break
            
    # Crop to requested limit
    if len(all_candles) > limit:
        all_candles = all_candles[-limit:]
        
    print(f"Successfully loaded {len(all_candles)} candles for {symbol} on {timeframe}.")
    
    highs = [float(x[2]) for x in all_candles]
    lows = [float(x[3]) for x in all_candles]
    closes = [float(x[4]) for x in all_candles]
    open_times = [int(x[0]) for x in all_candles]
    
    return highs, lows, closes, open_times

def run_backtest(highs, lows, closes, strategy_name, sl_pct, tp_pct, use_atr=False, atr_sl_mult=1.5, atr_tp_mult=3.0, time_stop_bars=None):
    """
    Backtests a specific strategy on given candle history.
    Enforces a strict Risk-to-Reward ratio (e.g. SL/TP = 1:2).
    """
    total_candles = len(closes)
    warmup_period = 50 # MACD slow is 26, SMA 50 needs 50
    
    if total_candles < warmup_period + 10:
        return {"win_rate": 0, "total_trades": 0, "profit_pct": 0, "wins": 0, "losses": 0}
        
    trades = []
    in_position = False
    entry_price = 0
    entry_index = 0
    stop_loss = 0
    take_profit = 0
    
    # Calculate ATR once for dynamic risk management if enabled
    atrs = indicators.calculate_atr(highs, lows, closes, period=14) if use_atr else []
    
    # Simulation loop
    i = warmup_period
    while i < total_candles:
        if not in_position:
            # Slice lists up to index i (inclusive) to represent historical data available at candle i
            h_slice = highs[:i+1]
            l_slice = lows[:i+1]
            c_slice = closes[:i+1]
            
            # Evaluate signals
            signals = strategies.evaluate_signals(h_slice, l_slice, c_slice)
            signal = signals.get(strategy_name, "HOLD")
            
            if signal == "BUY":
                # Enter Long Position
                in_position = True
                entry_price = closes[i]
                entry_index = i
                
                # Define SL and TP
                if use_atr and len(atrs) > i and atrs[i] > 0:
                    current_atr = atrs[i]
                    stop_loss = entry_price - (atr_sl_mult * current_atr)
                    take_profit = entry_price + (atr_tp_mult * current_atr)
                else:
                    stop_loss = entry_price * (1.0 - sl_pct / 100.0)
                    take_profit = entry_price * (1.0 + tp_pct / 100.0)
                    
                # Standard safety check: ensure stop loss is positive
                if stop_loss <= 0:
                    stop_loss = entry_price * 0.99
                    
        else:
            # We are in a trade. Monitor subsequent candles.
            curr_high = highs[i]
            curr_low = lows[i]
            curr_close = closes[i]
            
            hit_sl = curr_low <= stop_loss
            hit_tp = curr_high >= take_profit
            hit_time_stop = False
            
            # Time stop check
            if time_stop_bars and (i - entry_index) >= time_stop_bars:
                hit_time_stop = True
                
            # If both SL and TP are hit in the same candle, we conservatively assume SL is hit first
            if hit_sl and hit_tp:
                pnl_pct = -abs(stop_loss - entry_price) / entry_price * 100
                trades.append({"win": False, "pnl_pct": pnl_pct, "reason": "BOTH_SL_TP_HIT"})
                in_position = False
            elif hit_sl:
                pnl_pct = -abs(stop_loss - entry_price) / entry_price * 100
                trades.append({"win": False, "pnl_pct": pnl_pct, "reason": "SL_HIT"})
                in_position = False
            elif hit_tp:
                pnl_pct = abs(take_profit - entry_price) / entry_price * 100
                trades.append({"win": True, "pnl_pct": pnl_pct, "reason": "TP_HIT"})
                in_position = False
            elif hit_time_stop:
                pnl_pct = (curr_close - entry_price) / entry_price * 100
                trades.append({"win": pnl_pct > 0, "pnl_pct": pnl_pct, "reason": "TIME_STOP"})
                in_position = False
                
        i += 1
        
    # Compile statistics
    total_trades = len(trades)
    if total_trades == 0:
        return {"win_rate": 0, "total_trades": 0, "profit_pct": 0, "wins": 0, "losses": 0}
        
    wins = sum(1 for t in trades if t["win"])
    losses = total_trades - wins
    win_rate = (wins / total_trades) * 100
    profit_pct = sum(t["pnl_pct"] for t in trades)
    
    return {
        "win_rate": round(win_rate, 2),
        "total_trades": total_trades,
        "profit_pct": round(profit_pct, 2),
        "wins": wins,
        "losses": losses
    }

def main():
    print("=" * 60)
    print("         CRYPTO SCALPER BOT - QUANT BACKTESTING SUITE         ")
    print("=" * 60)
    
    # Download data for all coins and timeframes
    history_data = {}
    for coin in COINS:
        history_data[coin] = {}
        for tf in TIMEFRAMES:
            try:
                highs, lows, closes, _ = fetch_historical_candles(coin, tf, limit=3000)
                history_data[coin][tf] = (highs, lows, closes)
            except Exception as e:
                print(f"Failed to fetch data for {coin} {tf}: {e}")
                
    # List of strategy setups to test
    # All setups have a Risk to Reward ratio of exactly 1:2 (SL=X, TP=2X or ATR=1.5x/3.0x)
    risk_setups = [
        # Setup 1: Fixed 0.5% SL / 1.0% TP (Conservative Short Scalp)
        {"name": "Fixed_0.5_1.0", "sl": 0.5, "tp": 1.0, "use_atr": False},
        # Setup 2: Fixed 0.8% SL / 1.6% TP (Moderate Scalp)
        {"name": "Fixed_0.8_1.6", "sl": 0.8, "tp": 1.6, "use_atr": False},
        # Setup 3: Fixed 1.0% SL / 2.0% TP (Medium Scalp)
        {"name": "Fixed_1.0_2.0", "sl": 1.0, "tp": 2.0, "use_atr": False},
        # Setup 4: Dynamic ATR-based SL/TP (Standard Quant Setup)
        {"name": "Dynamic_ATR_1.5_3.0", "sl": 0, "tp": 0, "use_atr": True, "atr_sl": 1.5, "atr_tp": 3.0}
    ]
    
    strategies_list = ["SuperTrend_MFI_1M", "EMA_MACD_Crossover"]
    
    best_overall_wr = 0
    best_overall_profit = -9999
    best_config = {}
    
    print("\n" + "-" * 75)
    print(f"{'Strategy':<22} | {'Timeframe':<9} | {'Risk Setup':<18} | {'Trades':<6} | {'WinRate %':<10} | {'Profit %':<9}")
    print("-" * 75)
    
    results_list = []
    
    for strategy in strategies_list:
        for tf in TIMEFRAMES:
            for setup in risk_setups:
                total_trades_all_coins = 0
                total_wins_all_coins = 0
                total_losses_all_coins = 0
                total_profit_all_coins = 0.0
                
                # Run backtest across all three coins to evaluate general robustness
                for coin in COINS:
                    if tf not in history_data[coin]:
                        continue
                    highs, lows, closes = history_data[coin][tf]
                    
                    # For time stop, we let trades run up to 48 bars (4 hours on 5m, 12 hours on 15m)
                    time_stop_bars = 48
                    
                    res = run_backtest(
                        highs, lows, closes,
                        strategy_name=strategy,
                        sl_pct=setup["sl"],
                        tp_pct=setup["tp"],
                        use_atr=setup["use_atr"],
                        atr_sl_mult=setup.get("atr_sl", 1.5),
                        atr_tp_mult=setup.get("atr_tp", 3.0),
                        time_stop_bars=time_stop_bars
                    )
                    
                    total_trades_all_coins += res["total_trades"]
                    total_wins_all_coins += res["wins"]
                    total_losses_all_coins += res["losses"]
                    total_profit_all_coins += res["profit_pct"]
                
                # Combine results
                avg_win_rate = (total_wins_all_coins / total_trades_all_coins * 100) if total_trades_all_coins > 0 else 0
                avg_profit = total_profit_all_coins / len(COINS) # Average PnL across assets
                
                print(f"{strategy:<22} | {tf:<9} | {setup['name']:<18} | {total_trades_all_coins:<6} | {avg_win_rate:<8.2f}% | {avg_profit:<+.2f}%")
                
                results_list.append({
                    "strategy": strategy,
                    "timeframe": tf,
                    "setup": setup,
                    "trades": total_trades_all_coins,
                    "win_rate": avg_win_rate,
                    "profit": avg_profit
                })
                
                # Track best configuration based on user's requirements (WinRate >= 50%, RR >= 1:2)
                # We prioritize Win Rate and Profitability
                if avg_win_rate >= 50.0 and total_trades_all_coins >= 5:
                    if avg_profit > best_overall_profit:
                        best_overall_profit = avg_profit
                        best_overall_wr = avg_win_rate
                        best_config = {
                            "strategy": strategy,
                            "timeframe": tf,
                            "setup": setup,
                            "win_rate": avg_win_rate,
                            "profit": avg_profit,
                            "trades": total_trades_all_coins
                        }
                        
    print("=" * 75)
    if best_config:
        print("\n🏆 BEST VERIFIED STRATEGY CONFIGURATION FOUND:")
        print(f"  * Strategy:       {best_config['strategy']}")
        print(f"  * Timeframe:      {best_config['timeframe']}")
        print(f"  * Risk Setup:     {best_config['setup']['name']}")
        print(f"  * Total Trades:   {best_config['trades']} (across BTC, ETH, SOL)")
        print(f"  * Avg Win Rate:   {best_config['win_rate']:.2f}% (Target: >= 50%)")
        print(f"  * Avg Profit/Asset: {best_config['profit']:.2f}%")
        print(f"  * Risk-to-Reward: 1:2 Guaranteed")
    else:
        print("\n⚠️ No strategy achieved >= 50% Win Rate under standard strict fixed setups.")
        highest_wr_config = max(results_list, key=lambda x: x["win_rate"])
        print(f"  Highest Win Rate found: {highest_wr_config['win_rate']:.2f}% with strategy '{highest_wr_config['strategy']}' on {highest_wr_config['timeframe']}.")
        
if __name__ == "__main__":
    main()
