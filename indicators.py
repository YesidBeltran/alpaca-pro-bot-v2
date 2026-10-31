"""
Módulo de Indicadores Técnicos Institucionales
Cálculos vectorizados con Pandas y NumPy
"""
import numpy as np
import pandas as pd


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"].shift(1)

    tr1 = high - low
    tr2 = (high - close).abs()
    tr3 = (low - close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return atr


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    volume = df["volume"]
    cumulative_vp = (typical_price * volume).cumsum()
    cumulative_volume = volume.cumsum()
    vwap = cumulative_vp / cumulative_volume.replace(0, np.nan)
    return vwap.ffill().fillna(df["close"])


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df) < 14:
        return df

    data = df.copy()
    data["rsi"] = calculate_rsi(data["close"], period=14)
    data["atr"] = calculate_atr(data, period=14)
    data["vwap"] = calculate_vwap(data)
    data["ema_9"] = data["close"].ewm(span=9, adjust=False).mean()
    data["ema_21"] = data["close"].ewm(span=21, adjust=False).mean()
    data["sma_50"] = data["close"].rolling(window=min(len(data), 50)).mean()
    data["vol_sma"] = data["volume"].rolling(window=20).mean()
    return data
