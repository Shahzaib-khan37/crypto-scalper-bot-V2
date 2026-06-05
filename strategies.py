import indicators


def calculate_supertrend_local(highs, lows, closes, period=10, multiplier=3.0):
    """Supertrend (10, 3.0)"""
    if hasattr(indicators, 'calculate_supertrend'):
        return indicators.calculate_supertrend(highs, lows, closes, period, multiplier)
    
    if len(closes) < period + 1:
        return [], []
    
    atr = indicators.calculate_atr(highs, lows, closes, period)
    if not atr or len(atr) == 0:
        return [], []
    
    supertrend = []
    directions = []
    
    for _ in range(period + 1):
        supertrend.append(closes[period])
        directions.append(0)
    
    start_idx = period
    prev_close = closes[start_idx]
    prev_upper = (highs[start_idx] + lows[start_idx]) / 2 + multiplier * atr[start_idx]
    prev_lower = (highs[start_idx] + lows[start_idx]) / 2 - multiplier * atr[start_idx]
    prev_direction = 1 if prev_close > prev_upper else -1
    
    for i in range(period + 1, len(closes)):
        basic_upper = (highs[i] + lows[i]) / 2 + multiplier * atr[i]
        basic_lower = (highs[i] + lows[i]) / 2 - multiplier * atr[i]
        
        if basic_upper < prev_upper or closes[i-1] > prev_upper:
            final_upper = basic_upper
        else:
            final_upper = prev_upper
        
        if basic_lower > prev_lower or closes[i-1] < prev_lower:
            final_lower = basic_lower
        else:
            final_lower = prev_lower
        
        if prev_direction == 1:
            if closes[i] <= final_lower:
                direction = -1
            else:
                direction = 1
                final_lower = max(final_lower, prev_lower)
        else:
            if closes[i] >= final_upper:
                direction = 1
            else:
                direction = -1
                final_upper = min(final_upper, prev_upper)
        
        supertrend.append(final_lower if direction == 1 else final_upper)
        directions.append(direction)
        
        prev_upper = final_upper
        prev_lower = final_lower
        prev_direction = direction
    
    return supertrend, directions


def calculate_mfi(highs, lows, closes, volumes, period=14):
    """Money Flow Index (MFI)"""
    if len(closes) < period + 1:
        return []
    
    if not volumes or len(volumes) != len(closes):
        return indicators.calculate_rsi(closes, period)
    
    typical_prices = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(closes))]
    raw_money_flow = [tp * vol for tp, vol in zip(typical_prices, volumes)]
    
    positive_flow = []
    negative_flow = []
    
    for i in range(1, len(typical_prices)):
        if typical_prices[i] > typical_prices[i-1]:
            positive_flow.append(raw_money_flow[i])
            negative_flow.append(0)
        elif typical_prices[i] < typical_prices[i-1]:
            positive_flow.append(0)
            negative_flow.append(raw_money_flow[i])
        else:
            positive_flow.append(0)
            negative_flow.append(0)
    
    mfi_values = []
    
    for i in range(period, len(positive_flow) + 1):
        pos_sum = sum(positive_flow[i-period:i])
        neg_sum = sum(negative_flow[i-period:i])
        
        if neg_sum == 0:
            mfi_values.append(100)
        else:
            money_ratio = pos_sum / neg_sum
            mfi = 100 - (100 / (1 + money_ratio))
            mfi_values.append(mfi)
    
    pad = len(closes) - len(mfi_values)
    return [50] * pad + mfi_values


def evaluate_signals(highs, lows, closes, volumes=None):
    """
    ============================================================
    SUPERTREND (10,3) + MFI (14) — 1 MINUTE SCALPING
    ============================================================
    
    ENTRY (BUY) — 2/2 conditions:
      1. Supertrend Bullish Flip (Red → Green)
      2. MFI between 30-65
    
    EXIT (SELL) — 1/2 conditions:
      1. Supertrend Bearish Flip (Green → Red)
      2. MFI > 80
    
    SL/TP — Dynamic (bot.py handles)
    """
    
    signals = {
        "SuperTrend_MFI_1M": "HOLD",
        "EMA_MACD_Crossover": "HOLD"
    }
    
    if len(closes) < 35:
        return signals
    
    # --- Strategy 1: SuperTrend + MFI (Existing) ---
    try:
        # 1. Supertrend (10, 3.0)
        st_values, st_directions = calculate_supertrend_local(highs, lows, closes, period=10, multiplier=3.0)
        
        if len(st_directions) >= 2:
            prev_dir = st_directions[-2]
            curr_dir = st_directions[-1]
            
            # 2. MFI (14)
            mfi_values = calculate_mfi(highs, lows, closes, volumes, period=14)
            curr_mfi = mfi_values[-1] if mfi_values and len(mfi_values) > 0 else 50
            
            st_flip_bullish = (prev_dir == -1 and curr_dir == 1)
            mfi_buy_zone = (30 <= curr_mfi <= 65)
            
            if st_flip_bullish and mfi_buy_zone:
                signals["SuperTrend_MFI_1M"] = "BUY"
            elif (prev_dir == 1 and curr_dir == -1) or curr_mfi > 80:
                signals["SuperTrend_MFI_1M"] = "SELL"
    except Exception as e:
        print(f"Error in SuperTrend_MFI_1M: {e}")
        
    # --- Strategy 2: EMA Crossover + MACD Momentum (Optimized 15m Strategy) ---
    try:
        # Fast EMA (9), Slow EMA (21), MACD(12, 26, 9)
        fast_emas = indicators.calculate_ema(closes, period=9)
        slow_emas = indicators.calculate_ema(closes, period=21)
        macd_line, signal_line, histogram = indicators.calculate_macd(closes, fast_period=12, slow_period=26, signal_period=9)
        
        if len(fast_emas) >= 2 and len(slow_emas) >= 2 and len(macd_line) >= 2 and len(histogram) >= 2:
            prev_fast, curr_fast = fast_emas[-2], fast_emas[-1]
            prev_slow, curr_slow = slow_emas[-2], slow_emas[-1]
            curr_macd, curr_signal = macd_line[-1], signal_line[-1]
            curr_hist = histogram[-1]
            
            is_golden_cross = (prev_fast <= prev_slow) and (curr_fast > curr_slow)
            macd_bullish = (curr_macd > curr_signal) and (curr_hist > 0)
            
            is_death_cross = (prev_fast >= prev_slow) and (curr_fast < curr_slow)
            macd_bearish = (curr_hist < 0)
            
            if is_golden_cross and macd_bullish:
                signals["EMA_MACD_Crossover"] = "BUY"
            elif is_death_cross or macd_bearish:
                signals["EMA_MACD_Crossover"] = "SELL"
    except Exception as e:
        print(f"Error in EMA_MACD_Crossover: {e}")
    
    return signals