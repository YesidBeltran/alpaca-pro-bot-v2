import ta
def analyze(df):
    if len(df) < 60:
        return {"signal":None}
    df = df.copy()
    df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
    lookback = 20
    recent_high = df['high'].iloc[-lookback-1:-1].max()
    recent_low = df['low'].iloc[-lookback-1:-1].min()
    last = df.iloc[-1]
    prev = df.iloc[-2]
    swept_high = prev['high'] > recent_high and last['close'] < recent_high
    swept_low = prev['low'] < recent_low and last['close'] > recent_low
    if swept_low:
        return {"signal":"long","confidence":72,"reason":f"Sweep bajista fallido en {recent_low:.2f} + reclaim","atr":float(last['atr']),"strategy":"SMC"}
    if swept_high:
        return {"signal":"short","confidence":72,"reason":f"Sweep alcista fallido en {recent_high:.2f} + rechazo","atr":float(last['atr']),"strategy":"SMC"}
    return {"signal":None}
