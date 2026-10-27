import ta
def analyze(df):
    if len(df) < 50:
        return {"signal":None}
    df = df.copy()
    df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
    df['vol_avg'] = df['volume'].rolling(20).mean()
    last = df.iloc[-1]
    recent = df.iloc[-21:-1]
    range_high = recent['high'].max()
    range_low = recent['low'].min()
    range_size = range_high - range_low
    is_squeeze = range_size < (df['atr'].iloc[-21:-1].mean() * 1.3)
    vol_spike = last['volume'] > last['vol_avg'] * 1.7
    if is_squeeze and vol_spike:
        if last['close'] > range_high:
            return {"signal":"long","confidence":82,"reason":f"Breakout rango {range_low:.2f}-{range_high:.2f} vol x{last['volume']/last['vol_avg']:.1f}","atr":float(last['atr']),"strategy":"Breakout"}
        if last['close'] < range_low:
            return {"signal":"short","confidence":82,"reason":f"Breakdown rango {range_low:.2f}-{range_high:.2f} vol x{last['volume']/last['vol_avg']:.1f}","atr":float(last['atr']),"strategy":"Breakout"}
    return {"signal":None}
