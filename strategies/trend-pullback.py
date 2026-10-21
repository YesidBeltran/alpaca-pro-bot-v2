import pandas as pd

def ema(s, n): 
    return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    delta = s.diff()
    gain = delta.where(delta > 0, 0).rolling(n).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(n).mean()
    rs = gain / (loss.replace(0, 0.0001))
    return 100 - (100 / (1 + rs))

def atr(df, n=14):
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def analyze(df):
    if len(df) < 200:
        return {"signal": None}
        
    df = df.copy()
    df['ema20'] = ema(df['close'], 20)
    df['ema50'] = ema(df['close'], 50)
    df['ema200'] = ema(df['close'], 200)
    df['rsi'] = rsi(df['close'], 14)
    df['atr'] = atr(df, 14)
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Confirmación de macro-tendencia (EMA200)
    uptrend_macro = last['close'] > last['ema200']
    downtrend_macro = last['close'] < last['ema200']
    
    # LONG: Estructura alcista alineada
    if last['close'] > last['ema50'] and last['ema20'] > last['ema50'] and uptrend_macro:
        # Pullback controlado en zona neutra-alcista de RSI
        if 42 < last['rsi'] < 68:
            if last['close'] > prev['close']:  # Vela de confirmación alcista
                conf = 75 if (last['close'] > last['ema20']) else 68
                return {
                    "signal": "long",
                    "confidence": conf,
                    "reason": f"TrendPullback Bullish (EMA20>50>200, RSI {last['rsi']:.1f})",
                    "atr": float(last['atr']),
                    "strategy": "TrendPullback"
                }
                
    # SHORT: Estructura bajista alineada
    if last['close'] < last['ema50'] and last['ema20'] < last['ema50'] and downtrend_macro:
        if 32 < last['rsi'] < 58:
            if last['close'] < prev['close']:  # Vela de confirmación bajista
                conf = 75 if (last['close'] < last['ema20']) else 68
                return {
                    "signal": "short",
                    "confidence": conf,
                    "reason": f"TrendPullback Bearish (EMA20<50<200, RSI {last['rsi']:.1f})",
                    "atr": float(last['atr']),
                    "strategy": "TrendPullback"
                }
                
    return {"signal": None}
