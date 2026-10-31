"""
Detector de Régimen de Mercado (Macro Filter)
"""
from dataclasses import dataclass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed
import pandas as pd

from indicators import compute_all_indicators


@dataclass
class MarketRegime:
    name: str              # BULL_TREND, BEAR_TREND, CHOPPY_RANGE, HIGH_VOLATILITY
    confidence: float      # 0 a 100
    spy_price: float
    spy_rsi: float
    spy_above_vwap: bool
    summary: str


class MarketRegimeDetector:
    def __init__(self, data_client: StockHistoricalDataClient):
        self.data_client = data_client

    def evaluate_regime(self) -> MarketRegime:
        try:
            req = StockBarsRequest(
                symbol_or_symbols="SPY",
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                limit=100,
                feed=DataFeed.IEX,
            )
            df = self.data_client.get_stock_bars(req).df
            if df.empty:
                return MarketRegime("CHOPPY_RANGE", 50.0, 0.0, 50.0, False, "Sin datos de SPY")

            if isinstance(df.index, pd.MultiIndex):
                df = df.xs("SPY", level=0)

            df = compute_all_indicators(df)
            last = df.iloc[-1]

            price = float(last["close"])
            rsi = float(last["rsi"])
            vwap = float(last["vwap"])
            ema_9 = float(last["ema_9"])
            ema_21 = float(last["ema_21"])
            atr = float(last["atr"])
            avg_atr = float(df["atr"].tail(50).mean())

            above_vwap = price >= vwap
            trend_bull = ema_9 > ema_21 and price > ema_21
            trend_bear = ema_9 < ema_21 and price < ema_21

            if atr > avg_atr * 1.8:
                return MarketRegime(
                    name="HIGH_VOLATILITY",
                    confidence=85.0,
                    spy_price=round(price, 2),
                    spy_rsi=round(rsi, 1),
                    spy_above_vwap=above_vwap,
                    summary=f"SPY Volatilidad extrema (ATR ${atr:.2f} > promedio ${avg_atr:.2f})",
                )

            if trend_bull and above_vwap and rsi >= 50:
                conf = 75.0 + (15.0 if rsi < 70 else 0)
                return MarketRegime(
                    name="BULL_TREND",
                    confidence=min(conf, 95.0),
                    spy_price=round(price, 2),
                    spy_rsi=round(rsi, 1),
                    spy_above_vwap=True,
                    summary=f"SPY Alcista sobre VWAP (${vwap:.2f}) y EMA21. RSI {rsi:.0f}",
                )

            if trend_bear and not above_vwap and rsi < 48:
                return MarketRegime(
                    name="BEAR_TREND",
                    confidence=80.0,
                    spy_price=round(price, 2),
                    spy_rsi=round(rsi, 1),
                    spy_above_vwap=False,
                    summary=f"SPY Bajista bajo VWAP (${vwap:.2f}) y EMA21. RSI {rsi:.0f}",
                )

            return MarketRegime(
                name="CHOPPY_RANGE",
                confidence=60.0,
                spy_price=round(price, 2),
                spy_rsi=round(rsi, 1),
                spy_above_vwap=above_vwap,
                summary="SPY en consolidación o rango sin dirección clara.",
            )

        except Exception as e:
            return MarketRegime("CHOPPY_RANGE", 50.0, 0.0, 50.0, False, f"Error evaluando régimen: {e}")
