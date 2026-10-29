import pandas as pd
def atr(df, n=14):
    tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift()).abs(), (df['low']-df['close'].shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def analyze(df):
    if len(df) < 50:
        return {"signal":None}
    df = df.copy()
    df['atr'] = atr(df, 14)
    df['vol_avg'] = df['volume'].rolling(20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    last = df.iloc[-1]
    recent = df.iloc[-21:-1]
    range_high = recent['high'].max()
    range_low = recent['low'].min()
    is_squeeze = (range_high - range_low) < (df['atr'].iloc[-21:-1].mean() * 2.8)
    vol_spike = last['volume'] > last['vol_avg'] * 1.10 if last['vol_avg']>0 else True
    momentum = last['close'] > df['close'].iloc[-5]
    if (is_squeeze or momentum) and vol_spike:
        if last['close'] > range_high * 0.998:
            conf = 75 if vol_spike and is_squeeze else 62
            return {"signal":"long","confidence":conf,"reason":f"Breakout V11 {range_low:.1f}-{range_high:.1f} vol x{last['volume']/max(last['vol_avg'],1):.1f}","atr":float(last['atr']),"strategy":"Breakout"}
        if last['close'] < range_low * 1.002:
            conf = 75 if vol_spike and is_squeeze else 62
            return {"signal":"short","confidence":conf,"reason":f"Breakdown V11 {range_low:.1f}-{range_high:.1f} vol x{last['volume']/max(last['vol_avg'],1):.1f}","atr":float(last['atr']),"strategy":"Breakout"}
    if last['close'] > df['close'].iloc[-3] and last['close'] > last['ema50']:
        return {"signal":"long","confidence":62,"reason":"Momentum V11 + EMA50","atr":float(last['atr']),"strategy":"Breakout-MOM"}
    if last['close'] < df['close'].iloc[-3] and last['close'] < last['ema50']:
        return {"signal":"short","confidence":62,"reason":"Momentum V11 bear EMA50","atr":float(last['atr']),"strategy":"Breakout-MOM"}
    return {"signal":None}
