import math


# ============================================
# SMA (Simple Moving Average)
# ============================================
def calculate_sma(prices, period):
    if len(prices) < period:
        return []
    smas = []
    for i in range(len(prices) - period + 1):
        smas.append(sum(prices[i:i+period]) / period)
    return smas


# ============================================
# EMA (Exponential Moving Average)
# ============================================
def calculate_ema(prices, period):
    if len(prices) < period:
        return []
    
    multiplier = 2.0 / (period + 1.0)
    seed = sum(prices[:period]) / period
    emas = [seed]
    
    for price in prices[period:]:
        next_ema = (price - emas[-1]) * multiplier + emas[-1]
        emas.append(next_ema)
        
    return emas


# ============================================
# RSI (Relative Strength Index)
# ============================================
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return []
        
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        if diff > 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))
            
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    rsis = []
    if avg_loss == 0:
        rsis.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsis.append(100.0 - (100.0 / (1.0 + rs)))
        
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            rsis.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsis.append(100.0 - (100.0 / (1.0 + rs)))
            
    return rsis


# ============================================
# BOLLINGER BANDS
# ============================================
def calculate_bollinger_bands(prices, period=20, num_std_dev=2):
    if len(prices) < period:
        return [], [], []
        
    smas = calculate_sma(prices, period)
    upper_band = []
    lower_band = []
    
    for i in range(len(smas)):
        window = prices[i:i+period]
        mean = smas[i]
        variance = sum((x - mean) ** 2 for x in window) / period
        std_dev = math.sqrt(variance)
        
        upper_band.append(mean + (num_std_dev * std_dev))
        lower_band.append(mean - (num_std_dev * std_dev))
        
    return smas, upper_band, lower_band


# ============================================
# STOCHASTIC OSCILLATOR
# ============================================
def calculate_stochastic(highs, lows, closes, k_period=14, d_period=3):
    if len(highs) < k_period:
        return [], []
        
    k_values = []
    
    for i in range(len(closes) - k_period + 1):
        window_highs = highs[i:i+k_period]
        window_lows = lows[i:i+k_period]
        current_close = closes[i+k_period-1]
        
        highest_high = max(window_highs)
        lowest_low = min(window_lows)
        
        if highest_high == lowest_low:
            k = 50.0
        else:
            k = ((current_close - lowest_low) / (highest_high - lowest_low)) * 100.0
        k_values.append(k)
        
    d_values = calculate_sma(k_values, d_period)
    
    pad_len = len(k_values) - len(d_values)
    d_values = [50.0] * pad_len + d_values
    
    return k_values, d_values


# ============================================
# MACD (Moving Average Convergence Divergence)
# ============================================
def calculate_macd(prices, fast_period=12, slow_period=26, signal_period=9):
    if len(prices) < slow_period:
        return [], [], []
        
    fast_emas = calculate_ema(prices, fast_period)
    slow_emas = calculate_ema(prices, slow_period)
    
    align_idx = slow_period - fast_period
    fast_emas_aligned = fast_emas[align_idx:]
    
    macd_line = [f - s for f, s in zip(fast_emas_aligned, slow_emas)]
    
    if len(macd_line) < signal_period:
        return macd_line, [], []
        
    signal_line = calculate_ema(macd_line, signal_period)
    
    macd_aligned = macd_line[signal_period - 1:]
    histogram = [m - s for m, s in zip(macd_aligned, signal_line)]
    
    return macd_aligned, signal_line, histogram


# ============================================
# ATR (Average True Range)
# ============================================
def calculate_atr(highs, lows, closes, period=14):
    if len(closes) < 2:
        return []
        
    true_ranges = []
    for i in range(1, len(closes)):
        h = highs[i]
        l = lows[i]
        pc = closes[i-1]
        
        tr = max(h - l, abs(h - pc), abs(l - pc))
        true_ranges.append(tr)
        
    if len(true_ranges) < period:
        return [0.0] * len(closes)
        
    atrs = calculate_sma(true_ranges, period)
    
    pad_len = len(closes) - len(atrs)
    atrs = [atrs[0]] * pad_len + atrs
    
    return atrs


# ============================================
# VWAP (Volume Weighted Average Price)
# ============================================
def calculate_vwap(highs, lows, closes, volumes):
    """
    VWAP calculate karta hai.
    Agar volume data available nahi hai to SMA(20) fallback use karta hai.
    
    Formula:
        Typical Price = (High + Low + Close) / 3
        VWAP = Sum(Typical Price * Volume) / Sum(Volume)
    
    Returns: list of VWAP values (same length as closes)
    """
    if not volumes or len(volumes) != len(closes):
        # Fallback: Simple Moving Average of 20 candles
        vwap_fallback = []
        for i in range(len(closes)):
            if i >= 19:
                sma20 = sum(closes[i-19:i+1]) / 20
                vwap_fallback.append(sma20)
            else:
                vwap_fallback.append(closes[i])
        return vwap_fallback
    
    # Check if volume data is valid (not all zeros)
    total_vol = sum(volumes[-20:]) if len(volumes) >= 20 else sum(volumes)
    if total_vol == 0:
        vwap_fallback = []
        for i in range(len(closes)):
            if i >= 19:
                sma20 = sum(closes[i-19:i+1]) / 20
                vwap_fallback.append(sma20)
            else:
                vwap_fallback.append(closes[i])
        return vwap_fallback
    
    vwap_values = []
    cumulative_tp_vol = 0.0
    cumulative_vol = 0.0
    
    for i in range(len(closes)):
        typical_price = (highs[i] + lows[i] + closes[i]) / 3.0
        volume = volumes[i]
        
        cumulative_tp_vol += typical_price * volume
        cumulative_vol += volume
        
        if cumulative_vol > 0:
            vwap = cumulative_tp_vol / cumulative_vol
        else:
            vwap = closes[i]
        
        vwap_values.append(round(vwap, 8))
    
    return vwap_values


# ============================================
# SUPERTREND INDICATOR
# ============================================
def calculate_supertrend(highs, lows, closes, period=10, multiplier=3.0):
    """
    Supertrend Indicator calculate karta hai.
    
    Supertrend ek trend-following indicator hai jo ATR ka use karta hai.
    Green (1) = Bullish trend, Red (-1) = Bearish trend.
    
    Parameters:
        period: ATR ka period (default 10)
        multiplier: ATR multiplier for band width (default 3.0)
    
    Returns:
        supertrend_values: list of Supertrend line values
        supertrend_directions: list of directions (1 = Bullish, -1 = Bearish, 0 = No data)
    """
    if len(closes) < period + 1:
        return [], []
    
    # ATR calculate karein
    atr = calculate_atr(highs, lows, closes, period)
    if not atr or len(atr) == 0:
        return [], []
    
    supertrend = []
    directions = []
    
    # Pehle period+1 values ke liye placeholder
    for _ in range(period + 1):
        supertrend.append(closes[period])
        directions.append(0)
    
    # Initial values
    start_idx = period
    prev_close = closes[start_idx]
    prev_upper = (highs[start_idx] + lows[start_idx]) / 2.0 + multiplier * atr[start_idx]
    prev_lower = (highs[start_idx] + lows[start_idx]) / 2.0 - multiplier * atr[start_idx]
    prev_direction = 1 if prev_close > prev_upper else -1
    
    for i in range(period + 1, len(closes)):
        # Basic Bands
        basic_upper = (highs[i] + lows[i]) / 2.0 + multiplier * atr[i]
        basic_lower = (highs[i] + lows[i]) / 2.0 - multiplier * atr[i]
        
        # Final Upper Band
        if basic_upper < prev_upper or closes[i-1] > prev_upper:
            final_upper = basic_upper
        else:
            final_upper = prev_upper
        
        # Final Lower Band
        if basic_lower > prev_lower or closes[i-1] < prev_lower:
            final_lower = basic_lower
        else:
            final_lower = prev_lower
        
        # Direction Decision
        if prev_direction == 1:  # Pehle Bullish tha
            if closes[i] <= final_lower:
                direction = -1  # Bearish flip
            else:
                direction = 1  # Bullish continue
                final_lower = max(final_lower, prev_lower)
        else:  # Pehle Bearish tha
            if closes[i] >= final_upper:
                direction = 1  # Bullish flip
            else:
                direction = -1  # Bearish continue
                final_upper = min(final_upper, prev_upper)
        
        # Supertrend value
        if direction == 1:
            st_value = final_lower  # Bullish: support line
        else:
            st_value = final_upper  # Bearish: resistance line
        
        supertrend.append(st_value)
        directions.append(direction)
        
        prev_upper = final_upper
        prev_lower = final_lower
        prev_direction = direction
    
    return supertrend, directions


# ============================================
# ADX (Average Directional Index) - Optional
# ============================================
def calculate_adx(highs, lows, closes, period=14):
    """
    ADX calculate karta hai - trend ki strength measure karne ke liye.
    ADX > 25 = Strong trend, ADX < 20 = Weak/Ranging market.
    """
    if len(closes) < period + 1:
        return [0] * len(closes)
    
    tr_list = []
    plus_dm_list = []
    minus_dm_list = []
    
    for i in range(1, len(closes)):
        high_diff = highs[i] - highs[i-1]
        low_diff = lows[i-1] - lows[i]
        
        # True Range
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_list.append(tr)
        
        # +DM and -DM
        plus_dm = high_diff if high_diff > low_diff and high_diff > 0 else 0
        minus_dm = low_diff if low_diff > high_diff and low_diff > 0 else 0
        
        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)
    
    # Wilder's Smoothing
    atr_val = sum(tr_list[:period]) / period
    smoothed_plus_dm = sum(plus_dm_list[:period]) / period
    smoothed_minus_dm = sum(minus_dm_list[:period]) / period
    
    adx_values = [0] * period
    
    for i in range(period, len(tr_list)):
        atr_val = (atr_val * (period - 1) + tr_list[i]) / period
        smoothed_plus_dm = (smoothed_plus_dm * (period - 1) + plus_dm_list[i]) / period
        smoothed_minus_dm = (smoothed_minus_dm * (period - 1) + minus_dm_list[i]) / period
        
        plus_di = (smoothed_plus_dm / atr_val) * 100 if atr_val > 0 else 0
        minus_di = (smoothed_minus_dm / atr_val) * 100 if atr_val > 0 else 0
        
        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
        adx_values.append(dx)
    
    # Pad to match input length
    while len(adx_values) < len(closes):
        adx_values.insert(0, 0)
    
    return adx_values