import pandas as pd
def atr(df, n=14):
    tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift()).abs(), (df['low']-df['close'].shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def analyze(df):
    if len(df) < 60:
        return {"signal":None}
    df = df.copy()
    df['atr'] = atr(df, 14)
    lookback = 20
    recent_high = df['high'].iloc[-lookback-1:-1].max()
    recent_low = df['low'].iloc[-lookback-1:-1].min()
    last = df.iloc[-1]
    prev = df.iloc[-2]
    swept_low = prev['low'] < recent_low and last['close'] > recent_low
    swept_high = prev['high'] > recent_high and last['close'] < recent_high
    if swept_low:
        return {"signal":"long","confidence":72,"reason":f"Sweep bajista fallido en {recent_low:.2f} + reclaim","atr":float(last['atr']),"strategy":"SMC"}
    if swept_high:
        return {"signal":"short","confidence":72,"reason":f"Sweep alcista fallido en {recent_high:.2f} + rechazo","atr":float(last['atr']),"strategy":"SMC"}
    return {"signal":None}
