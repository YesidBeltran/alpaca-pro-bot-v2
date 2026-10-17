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
    if len(df) < 200:
        return {"signal": None}
    df = df.copy()
    df['ema50'] = ema(df['close'], 50)
    df['ema200'] = ema(df['close'], 200)
    df['rsi'] = rsi(df['close'], 14)
    df['atr'] = atr(df, 14)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    touched = (df['low'].iloc[-6:-1] <= df['ema50'].iloc[-6:-1]).any()
    if last['close'] > last['ema200'] and last['close'] > last['ema50']:
        bullish = last['close'] > prev['open'] and last['close'] > prev['high']
        if touched and bullish and 40 < last['rsi'] < 68:
            return {"signal":"long","confidence":78,"reason":f"Tendencia alcista + pullback EMA50 RSI {last['rsi']:.1f}","atr":float(last['atr']),"strategy":"TrendPullback"}
    touched_bear = (df['high'].iloc[-6:-1] >= df['ema50'].iloc[-6:-1]).any()
    if last['close'] < last['ema200'] and last['close'] < last['ema50']:
        bearish = last['close'] < prev['open'] and last['close'] < prev['low']
        if touched_bear and bearish and 32 < last['rsi'] < 60:
            return {"signal":"short","confidence":78,"reason":f"Tendencia bajista + pullback EMA50 RSI {last['rsi']:.1f}","atr":float(last['atr']),"strategy":"TrendPullback"}
    return {"signal":None}
