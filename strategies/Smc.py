import pandas as pd
def atr(df, n=14):
    tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift()).abs(), (df['low']-df['close'].shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def analyze(df):
    if len(df) < 40:
        return {"signal":None}
    df = df.copy()
    df['atr'] = atr(df, 14)
    lookback = 12
    recent_high = df['high'].iloc[-lookback-1:-1].max()
    recent_low = df['low'].iloc[-lookback-1:-1].min()
    last = df.iloc[-1]
    prev = df.iloc[-2]
    swept_low = prev['low'] <= recent_low * 1.001 and last['close'] > recent_low
    swept_high = prev['high'] >= recent_high * 0.999 and last['close'] < recent_high
    if swept_low:
        return {"signal":"long","confidence":62,"reason":f"SMC Sweep low V11 {recent_low:.1f} reclaim","atr":float(last['atr']),"strategy":"SMC"}
    if swept_high:
        return {"signal":"short","confidence":62,"reason":f"SMC Sweep high V11 {recent_high:.1f} rechazo","atr":float(last['atr']),"strategy":"SMC"}
    if last['close'] > recent_high * 0.997 and last['close'] > df['close'].iloc[-3]:
        return {"signal":"long","confidence":54,"reason":"SMC OB reclaim V11","atr":float(last['atr']),"strategy":"SMC-OB"}
    if last['close'] < recent_low * 1.003 and last['close'] < df['close'].iloc[-3]:
        return {"signal":"short","confidence":54,"reason":"SMC OB breakdown V11","atr":float(last['atr']),"strategy":"SMC-OB"}
    return {"signal":None}
