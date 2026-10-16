import ta
def analyze(df):
    if len(df) < 200:
        return {"signal": None}
    df = df.copy()
    df['ema50'] = ta.trend.ema_indicator(df['close'], window=50)
    df['ema200'] = ta.trend.ema_indicator(df['close'], window=200)
    df['rsi'] = ta.momentum.rsi(df['close'], window=14)
    df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    touched_ema50 = (df['low'].iloc[-6:-1] <= df['ema50'].iloc[-6:-1]).any()
    if last['close'] > last['ema200'] and last['close'] > last['ema50']:
        bullish = last['close'] > prev['open'] and last['close'] > prev['high']
        if touched_ema50 and bullish and 40 < last['rsi'] < 68:
            return {"signal":"long","confidence":78,"reason":f"Tendencia alcista + pullback EMA50 RSI {last['rsi']:.1f}","atr":float(last['atr']),"strategy":"TrendPullback"}
    touched_ema50_bear = (df['high'].iloc[-6:-1] >= df['ema50'].iloc[-6:-1]).any()
    if last['close'] < last['ema200'] and last['close'] < last['ema50']:
        bearish = last['close'] < prev['open'] and last['close'] < prev['low']
        if touched_ema50_bear and bearish and 32 < last['rsi'] < 60:
            return {"signal":"short","confidence":78,"reason":f"Tendencia bajista + pullback EMA50 RSI {last['rsi']:.1f}","atr":float(last['atr']),"strategy":"TrendPullback"}
    return {"signal":None}
