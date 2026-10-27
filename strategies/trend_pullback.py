import pandas as pd
def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rsi(s, n=14):
    delta = s.diff()
    gain = delta.where(delta>0,0).rolling(n).mean()
    loss = (-delta.where(delta<0,0)).rolling(n).mean()
    rs = gain / (loss.replace(0,0.0001))
    return 100 - (100/(1+rs))
def atr(df, n=14):
    tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift()).abs(), (df['low']-df['close'].shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def analyze(df):
    if len(df) < 100:
        return {"signal": None}
    df = df.copy()
    df['ema20'] = ema(df['close'], 20)
    df['ema50'] = ema(df['close'], 50)
    df['ema200'] = ema(df['close'], 200)
    df['rsi'] = rsi(df['close'], 14)
    df['atr'] = atr(df, 14)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if last['close'] > last['ema50'] and last['ema20'] > last['ema50']:
        if 35 < last['rsi'] < 72:
            if last['close'] > prev['close']:
                return {"signal":"long","confidence":65,"reason":f"TrendPull V11 bull EMA20>50 RSI {last['rsi']:.0f}","atr":float(last['atr']),"strategy":"TrendPullback"}
    if last['close'] < last['ema50'] and last['ema20'] < last['ema50']:
        if 28 < last['rsi'] < 65:
            if last['close'] < prev['close']:
                return {"signal":"short","confidence":65,"reason":f"TrendPull V11 bear EMA20<50 RSI {last['rsi']:.0f}","atr":float(last['atr']),"strategy":"TrendPullback"}
    if last['close'] > last['ema20'] and prev['close'] <= df['ema20'].iloc[-2] and last['rsi'] < 70:
        return {"signal":"long","confidence":60,"reason":"EMA20 reclaim V11","atr":float(last['atr']),"strategy":"Trend-EMA20"}
    if last['close'] < last['ema20'] and prev['close'] >= df['ema20'].iloc[-2] and last['rsi'] > 30:
        return {"signal":"short","confidence":60,"reason":"EMA20 breakdown V11","atr":float(last['atr']),"strategy":"Trend-EMA20"}
    return {"signal":None}
