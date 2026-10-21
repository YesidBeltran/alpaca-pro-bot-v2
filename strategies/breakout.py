import pandas as pd

def atr(df, n=14):
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def analyze(df):
    if len(df) < 50:
        return {"signal": None}
        
    df = df.copy()
    df['atr'] = atr(df, 14)
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    last = df.iloc[-1]
    recent = df.iloc[-21:-1]
    range_high = recent['high'].max()
    range_low = recent['low'].min()
    
    # Compresión de volatilidad (Squeeze real)
    is_squeeze = (range_high - range_low) < (df['atr'].iloc[-21:-1].mean() * 2.2)
    vol_spike = last['volume'] > last['vol_avg'] * 1.35 if last['vol_avg'] > 0 else False
    
    if is_squeeze and vol_spike:
        if last['close'] > range_high:
            return {
                "signal": "long",
                "confidence": 80,
                "reason": f"Breakout Squeeze Confirmado ({range_low:.2f}-{range_high:.2f}) Vol x{last['volume']/max(last['vol_avg'],1):.1f}",
                "atr": float(last['atr']),
                "strategy": "Breakout"
            }
        if last['close'] < range_low:
            return {
                "signal": "short",
                "confidence": 80,
                "reason": f"Breakdown Squeeze Confirmado ({range_low:.2f}-{range_high:.2f}) Vol x{last['volume']/max(last['vol_avg'],1):.1f}",
                "atr": float(last['atr']),
                "strategy": "Breakout"
            }
            
    # Momentum breakout con volumen (sin squeeze estricto pero con spike alto)
    if vol_spike:
        if last['close'] > range_high and last['close'] > last['ema50']:
            return {
                "signal": "long",
                "confidence": 70,
                "reason": f"Momentum Breakout Vol Spike x{last['volume']/max(last['vol_avg'],1):.1f}",
                "atr": float(last['atr']),
                "strategy": "Breakout-MOM"
            }
        if last['close'] < range_low and last['close'] < last['ema50']:
            return {
                "signal": "short",
                "confidence": 70,
                "reason": f"Momentum Breakdown Vol Spike x{last['volume']/max(last['vol_avg'],1):.1f}",
                "atr": float(last['atr']),
                "strategy": "Breakout-MOM"
            }
            
    return {"signal": None}
