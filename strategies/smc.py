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
    
    lookback = 15
    recent_high = df['high'].iloc[-lookback-1:-1].max()
    recent_low = df['low'].iloc[-lookback-1:-1].min()
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Exigir volumen superior al promedio para confirmar sweep/reclamation inteligente
    has_vol = last['volume'] > last['vol_avg'] * 1.15 if last['vol_avg'] > 0 else True
    
    # SMC Sweep Low (Liquidity Grab) + Reclaim con filtro estricto
    swept_low = prev['low'] <= recent_low * 1.0005 and last['close'] > recent_low
    swept_high = prev['high'] >= recent_high * 0.9995 and last['close'] < recent_high
    
    if swept_low and has_vol:
        conf = 78 if last['volume'] > last['vol_avg'] * 1.4 else 68
        return {
            "signal": "long",
            "confidence": conf,
            "reason": f"SMC Sweep Low Reclaim ({recent_low:.2f}) con Confirmación Vol",
            "atr": float(last['atr']),
            "strategy": "SMC-Sweep"
        }
        
    if swept_high and has_vol:
        conf = 78 if last['volume'] > last['vol_avg'] * 1.4 else 68
        return {
            "signal": "short",
            "confidence": conf,
            "reason": f"SMC Sweep High Rechazo ({recent_high:.2f}) con Confirmación Vol",
            "atr": float(last['atr']),
            "strategy": "SMC-Sweep"
        }
        
    # SMC Order Block / Imbalance Reclaim
    if last['close'] > recent_high * 0.998 and last['close'] > df['close'].iloc[-3] and has_vol:
        return {
            "signal": "long",
            "confidence": 66,
            "reason": f"SMC Order Block Reclaim ({last['close']:.2f})",
            "atr": float(last['atr']),
            "strategy": "SMC-OB"
        }
        
    if last['close'] < recent_low * 1.002 and last['close'] < df['close'].iloc[-3] and has_vol:
        return {
            "signal": "short",
            "confidence": 66,
            "reason": f"SMC Order Block Breakdown ({last['close']:.2f})",
            "atr": float(last['atr']),
            "strategy": "SMC-OB"
        }
        
    return {"signal": None}
