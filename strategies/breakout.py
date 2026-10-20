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
    last = df.iloc[-1]
    recent = df.iloc[-21:-1]
    range_high = recent['high'].max()
    range_low = recent['low'].min()
    is_squeeze = (range_high - range_low) < (df['atr'].iloc[-21:-1].mean() * 1.6)
    vol_spike = last['volume'] > last['vol_avg'] * 1.4 if last['vol_avg']>0 else False
    if is_squeeze and vol_spike:
        if last['close'] > range_high:
            return {"signal":"long","confidence":82,"reason":f"Breakout {range_low:.2f}-{range_high:.2f} vol x{last['volume']/last['vol_avg']:.1f}","atr":float(last['atr']),"strategy":"Breakout"}
        if last['close'] < range_low:
            return {"signal":"short","confidence":82,"reason":f"Breakdown {range_low:.2f}-{range_high:.2f} vol x{last['volume']/last['vol_avg']:.1f}","atr":float(last['atr']),"strategy":"Breakout"}
    return {"signal":None}
