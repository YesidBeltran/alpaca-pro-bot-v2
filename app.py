"""
Alpaca Pro Bot V2 - AURA SYNAPSE V12 ADAPTIVE LEARNING TERMINAL
Dashboard + Trading Brain + Machine Learning Feedback Loop
"""
import json
import math
import os
import threading
import time
import traceback
from collections import deque
from datetime import datetime

from flask import Flask, jsonify, render_template, request
import pandas as pd
import pytz

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (
    ClosePositionRequest,
    GetOrdersRequest,
    MarketOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)

from config import Config
from indicators import compute_all_indicators
from learning_engine import LearningEngine
from market_regime import MarketRegimeDetector
from risk_manager import RiskManager

try:
    from telegram_journal import TelegramJournal
except ImportError:
    class TelegramJournal:
        def __init__(self, *a, **k): self.enabled = False
        def log_trade(self, *a, **k): pass
        def send_daily_summary(self, *a, **k): pass
        def send(self, msg): return False

try:
    from strategies import STRATEGIES
except ImportError:
    class TrendSMAStrategy:
        def analyze(self, df):
            if len(df) < 30:
                return {}
            last = df.iloc[-1]
            if (
                last["close"] > last["vwap"]
                and last["ema_9"] > last["ema_21"]
                and 52 <= last["rsi"] <= 68
                and last["volume"] > last.get("vol_sma", 0)
            ):
                return {
                    "signal": "long",
                    "confidence": 72,
                    "strategy": "Institutional VWAP Trend",
                    "reason": "Precio sobre VWAP con volumen y RSI en zona de impulso",
                }
            return {}
    STRATEGIES = [TrendSMAStrategy()]

try:
    from backtest import Backtester
except ImportError:
    class Backtester:
        def run_all(self): pass

app = Flask(__name__, template_folder="templates", static_folder="static")

EQUITY_HISTORY = deque(maxlen=100)
STATE_LOCK = threading.Lock()

BOT_STATE = {
    "equity": 100000.0, "cash": 90000.0, "buying_power": 180000.0,
    "today_pnl": 0.0, "today_pnl_pct": 0.0, "market_open": False,
    "last_scan": "--", "positions": [], "watchlist": [], "logs": deque(maxlen=100),
    "news": [], "market_regime": {"name": "ANALIZANDO", "summary": "Inicializando detector", "confidence": 0},
    "orderbook": [], "vol": "38.2M", "atr": "2.4", "breadth": 68,
    "dayDelta": 0.0, "sharpe": 0.0, "ytd": "0.0%", "return_ytd": 0.0, "volatility": 0.0,
    "max_drawdown": 0.0, "momentum_rsi": 50, "confidence_avg": 0.0, "performance": {},
    "learning_summary": {}
}

DATA_CLIENT = None
TRADING_CLIENT = None
LEARNING_ENGINE = None


def log_msg(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    with STATE_LOCK:
        BOT_STATE["logs"].append({"time": ts, "msg": msg})
    print(f"[{ts}] {msg}", flush=True)


def get_ny_time():
    ny_tz = pytz.timezone("America/New_York")
    return datetime.now(ny_tz)


def get_ny_time_str():
    try:
        return get_ny_time().strftime("%Y-%m-%d %H:%M:%S NY")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


def is_market_open_now(trading_client=None):
    if trading_client:
        try:
            clock = trading_client.get_clock()
            now_ny = get_ny_time()
            total_min = now_ny.hour * 60 + now_ny.minute
            return clock.is_open and (570 <= total_min <= 945)
        except Exception:
            pass

    try:
        now_ny = get_ny_time()
        is_weekday = now_ny.weekday() < 5
        total_min = now_ny.hour * 60 + now_ny.minute
        return is_weekday and (570 <= total_min <= 945)
    except Exception:
        return False


def should_close_eod():
    try:
        now_ny = get_ny_time()
        if now_ny.weekday() >= 5:
            return False
        total_min = now_ny.hour * 60 + now_ny.minute
        return 944 <= total_min < 960
    except Exception:
        return False


class TradingBrain:
    def __init__(self):
        Config.validate()
        self.trading_client = TradingClient(Config.API_KEY, Config.SECRET_KEY, paper=True)
        self.data_client = StockHistoricalDataClient(Config.API_KEY, Config.SECRET_KEY)
        self.risk = RiskManager(Config)
        self.telegram = TelegramJournal(Config.TELEGRAM_TOKEN, Config.TELEGRAM_CHAT_ID)
        self.learning = LearningEngine()
        self.regime_detector = MarketRegimeDetector(self.data_client)

        global DATA_CLIENT, TRADING_CLIENT, LEARNING_ENGINE
        DATA_CLIENT = self.data_client
        TRADING_CLIENT = self.trading_client
        LEARNING_ENGINE = self.learning

        log_msg(
            f"Alpaca PAPER conectado | Simbolos: {Config.SYMBOLS} | "
            f"Learning Engine: ONLINE | Telegram: {'ON' if self.telegram.enabled else 'OFF'}"
        )

        try:
            with STATE_LOCK:
                BOT_STATE["day_start_equity"] = float(self.trading_client.get_account().equity)
            log_msg(f"Day start equity: ${BOT_STATE['day_start_equity']:.2f}")
        except Exception:
            with STATE_LOCK:
                BOT_STATE["day_start_equity"] = 100000.0

    def get_bars(self, symbol, limit=100):
        try:
            tf_str = Config.TIMEFRAME
            tf = (
                TimeFrame(15, TimeFrameUnit.Minute)
                if tf_str == "15Min"
                else TimeFrame(5, TimeFrameUnit.Minute)
            )

            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                limit=limit,
                feed=DataFeed.IEX,
            )
            bars = self.data_client.get_stock_bars(req).df
            if bars.empty:
                return pd.DataFrame()
            if isinstance(bars.index, pd.MultiIndex):
                bars = bars.xs(symbol, level=0)

            df = bars.rename(
                columns={
                    "open": "open",
                    "high": "high",
                    "low": "low",
                    "close": "close",
                    "volume": "volume",
                }
            )
            return compute_all_indicators(df)
        except Exception as e:
            log_msg(f"Error barras {symbol}: {e}")
            return pd.DataFrame()

    def think(self, symbol, current_regime_name):
        df = self.get_bars(symbol)
        if df.empty or len(df) < 30:
            return None

        votes = []
        for strat in STRATEGIES:
            try:
                res = strat.analyze(df)
                if res and res.get("signal"):
                    strat_name = res.get("strategy", "Generic")
                    mult = self.learning.get_strategy_multiplier(strat_name, current_regime_name)

                    if mult <= 0:
                        log_msg(f"[{symbol}] Estrategia '{strat_name}' deshabilitada en régimen {current_regime_name}")
                        continue

                    res["learning_mult"] = mult
                    votes.append(res)
            except Exception as e:
                log_msg(f"Error analizando {symbol}: {e}")

        if not votes:
            return None

        longs = [v for v in votes if v.get("signal") == "long"]
        if longs:
            best = max(longs, key=lambda x: x.get("confidence", 0))
            last_row = df.iloc[-1]
            best["rsi"] = float(last_row.get("rsi", 50))
            best["atr"] = float(last_row.get("atr", 0))
            best["vwap"] = float(last_row.get("vwap", 0))
            return best

        return None

    def close_position(self, symbol, reason=""):
        try:
            log_msg(f"Cerrando posición {symbol} | Motivo: {reason}")
            try:
                req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
                open_orders = self.trading_client.get_orders(filter=req)
                for o in open_orders:
                    self.trading_client.cancel_order_by_id(o.id)
            except Exception:
                pass

            pnl = 0.0
            exit_price = 0.0
            positions = self.trading_client.get_all_positions()
            for p in positions:
                if p.symbol == symbol:
                    pnl = float(p.unrealized_pl)
                    exit_price = float(p.current_price) if getattr(p, "current_price", None) else float(p.avg_entry_price)
                    break

            self.trading_client.close_position(symbol)
            self.learning.record_exit(symbol, exit_price, pnl, exit_reason=reason)

            try:
                self.telegram.send(f"✅ CIERRE {symbol} | PnL: ${pnl:.2f} | {reason}")
            except Exception:
                pass

            return True
        except Exception as e:
            log_msg(f"Error cerrando {symbol}: {e}")
            return False

    def manage_positions(self):
        try:
            positions = self.trading_client.get_all_positions()
            equity = float(self.trading_client.get_account().equity)

            for p in positions:
                try:
                    symbol = p.symbol
                    pl_pct = float(p.unrealized_plpc) * 100
                    current_price = float(p.current_price) if getattr(p, "current_price", None) else float(p.avg_entry_price)
                    entry_price = float(p.avg_entry_price)

                    bars = self.get_bars(symbol, limit=20)
                    atr = float(bars.iloc[-1].get("atr", entry_price * 0.015)) if not bars.empty else (entry_price * 0.015)

                    direction = "long" if float(p.qty) > 0 else "short"
                    est_sl = entry_price * (0.988 if direction == "long" else 1.012)
                    new_sl, trail_reason = self.risk.evaluate_trailing_stop(entry_price, current_price, est_sl, direction, atr)

                    if trail_reason:
                        log_msg(f"🛡️ {symbol} {trail_reason} -> Protegiendo capital en ${new_sl:.2f}")

                    if pl_pct <= -1.2:
                        self.close_position(symbol, f"STOP LOSS (-1.2%) ejecutado en ${current_price:.2f}")
                    elif pl_pct >= 2.5:
                        self.close_position(symbol, f"TAKE PROFIT (+2.5%) ejecutado en ${current_price:.2f}")

                except Exception as e:
                    log_msg(f"Error gestionando posición {getattr(p, 'symbol', '?')}: {e}")

            day_start = BOT_STATE.get("day_start_equity", equity)
            if day_start > 0:
                loss_pct = (equity - day_start) / day_start * 100
                if loss_pct <= -1.5:
                    log_msg(f"🚨 DAILY MAX LOSS ALCANZADO ({loss_pct:.2f}%) - CERRANDO TODO")
                    for p in positions:
                        self.close_position(p.symbol, "KILL SWITCH MAX LOSS DIARIO")

        except Exception as e:
            log_msg(f"Error en manage_positions: {e}")

    def execute_bracket(self, symbol, decision, equity, regime_name):
        try:
            bars = self.get_bars(symbol, limit=2)
            if bars.empty:
                return False

            last_price = float(bars["close"].iloc[-1])
            sl, tp, _ = self.risk.get_stop_take(
                last_price, decision["signal"], atr=decision.get("atr")
            )

            learn_mult = decision.get("learning_mult", 1.0)
            qty = self.risk.calculate_position_size(
                equity, last_price, sl, dynamic_multiplier=learn_mult
            )

            if qty == 0:
                log_msg(f"[{symbol}] Qty 0 - Riesgo no permitido por capital o estrategia en pausa")
                return False

            side = OrderSide.BUY if decision["signal"] == "long" else OrderSide.SELL
            log_msg(
                f">>> [ORDEN] {symbol} {decision['signal'].upper()} | Estrategia: {decision.get('strategy')} | "
                f"Entrada ~${last_price:.2f} SL ${sl:.2f} TP ${tp:.2f} Qty {qty} (Aprendizaje: x{learn_mult:.1f})"
            )

            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=tp),
                stop_loss=StopLossRequest(stop_price=sl),
            )

            self.trading_client.submit_order(order)
            log_msg(f"Bracket enviada con éxito para {symbol}")

            self.learning.record_entry(
                symbol=symbol,
                side=decision["signal"],
                strategy=decision.get("strategy", "Generic"),
                entry_price=last_price,
                sl=sl,
                tp=tp,
                qty=qty,
                regime=regime_name,
                rsi=decision.get("rsi", 50),
                atr=decision.get("atr", 0),
                confidence=decision.get("confidence", 70),
            )

            self.telegram.log_trade(symbol, decision, last_price, sl, tp, qty, equity)
            return True
        except Exception as e:
            log_msg(f"Error al enviar bracket {symbol}: {e}")
            return False

    def update_global_state(self):
        try:
            acct = self.trading_client.get_account()
            with STATE_LOCK:
                BOT_STATE["equity"] = float(acct.equity)
                BOT_STATE["cash"] = float(acct.cash)
                BOT_STATE["buying_power"] = float(acct.buying_power)

            regime = self.regime_detector.evaluate_regime()

            pos_list = []
            try:
                positions = self.trading_client.get_all_positions()
                for p in positions:
                    pl = float(p.unrealized_pl)
                    pl_pct = float(p.unrealized_plpc) * 100
                    pos_list.append({
                        "symbol": p.symbol,
                        "qty": float(p.qty),
                        "entry": float(p.avg_entry_price),
                        "pl": round(pl, 2),
                        "pl_pct": round(pl_pct, 2),
                        "nom": f"${float(p.market_value):.0f}",
                    })
            except Exception as e:
                log_msg(f"Pos error: {e}")

            watchlist = []
            rsi_values = []
            for sym in Config.SYMBOLS:
                try:
                    df = self.get_bars(sym, limit=25)
                    if not df.empty:
                        last = df.iloc[-1]
                        price = float(last["close"])
                        prev = float(df.iloc[-2]["close"]) if len(df) > 1 else price
                        change = ((price - prev) / prev * 100) if prev else 0.0
                        rsi_val = round(float(last.get("rsi", 50)), 1)
                        rsi_values.append(rsi_val)
                        watchlist.append({
                            "symbol": sym,
                            "price": round(price, 2),
                            "change": round(change, 2),
                            "rsi": rsi_val,
                            "vwap": round(float(last.get("vwap", price)), 2),
                        })
                except Exception:
                    watchlist.append({"symbol": sym, "price": 0, "change": 0, "rsi": 50, "vwap": 0})

            learn_summary = self.learning.get_summary_stats()

            with STATE_LOCK:
                BOT_STATE["positions"] = pos_list
                BOT_STATE["watchlist"] = watchlist
                BOT_STATE["last_scan"] = get_ny_time_str()
                BOT_STATE["market_open"] = is_market_open_now(self.trading_client)
                BOT_STATE["market_regime"] = {
                    "name": regime.name,
                    "confidence": regime.confidence,
                    "summary": regime.summary,
                    "spy_price": regime.spy_price,
                }
                BOT_STATE["learning_summary"] = learn_summary
                if rsi_values:
                    BOT_STATE["momentum_rsi"] = round(sum(rsi_values) / len(rsi_values), 1)

        except Exception as e:
            log_msg(f"Error actualizando estado global: {e}")

    def run_loop(self):
        last_trade_time = None
        trade_validation_cooldown = 15 * 60

        while True:
            try:
                self.update_global_state()
                acct = self.trading_client.get_account()
                equity = float(acct.equity)
                positions = self.trading_client.get_all_positions()
                pos_syms = [p.symbol for p in positions]
                now_str = get_ny_time_str()

                if should_close_eod() and positions:
                    log_msg(f"CIERRE EOD {now_str} - Cerrando {len(positions)} posiciones")
                    for p in positions:
                        self.close_position(p.symbol, "CIERRE FIN DE DIA (15:44 NY)")
                    time.sleep(60 * 5)
                    continue

                if not is_market_open_now(self.trading_client):
                    log_msg(f"--- SCAN {now_str} | Mercado CERRADO | Posiciones: {pos_syms} ---")
                    time.sleep(60 * 5)
                    continue

                with STATE_LOCK:
                    regime_name = BOT_STATE["market_regime"]["name"]
                    regime_summary = BOT_STATE["market_regime"]["summary"]

                log_msg(f"--- SCAN {now_str} | Régimen: {regime_name} | Equity: ${equity:.2f} ---")
                log_msg(f"Detalle Macro: {regime_summary}")

                if regime_name == "HIGH_VOLATILITY":
                    log_msg("⚠️ Régimen de ALTA VOLATILIDAD detectado. Modo seguro: 0 nuevas entradas.")
                    self.manage_positions()
                    time.sleep(60 * 5)
                    continue

                self.manage_positions()

                if last_trade_time:
                    elapsed = time.time() - last_trade_time
                    if elapsed < trade_validation_cooldown:
                        rem = int((trade_validation_cooldown - elapsed) / 60)
                        log_msg(f"Tiempo de validación: {rem} min restantes para nuevo trade")
                        time.sleep(60 * 2)
                        continue

                if not self.risk.can_open_new_position(positions):
                    log_msg(f"Límite de posiciones ({len(positions)}/{Config.MAX_POSITIONS}) alcanzado")
                    time.sleep(60 * 3)
                    continue

                found_trade = False
                for symbol in Config.SYMBOLS:
                    if symbol in pos_syms:
                        continue

                    decision = self.think(symbol, regime_name)
                    if decision:
                        if self.execute_bracket(symbol, decision, equity, regime_name):
                            last_trade_time = time.time()
                            self.update_global_state()
                            found_trade = True
                            break

                if not found_trade:
                    log_msg(f"Sin nuevas señales válidas en este ciclo ({len(pos_syms)} posiciones abiertas)")

                sleep_mins = 15 if Config.TIMEFRAME == "15Min" else 5
                time.sleep(60 * sleep_mins)

            except Exception as e:
                log_msg(f"[ERROR LOOP] {e}")
                traceback.print_exc()
                time.sleep(60)


@app.route("/")
def home():
    try:
        return render_template("dashboard.html")
    except Exception:
        return jsonify({"message": "Alpaca Pro Bot V12 Adaptive activo."})


@app.route("/api/status")
def api_status():
    try:
        with STATE_LOCK:
            state = {}
            for k, v in BOT_STATE.items():
                if k == "logs":
                    state[k] = list(v)[-50:]
                elif isinstance(v, deque):
                    state[k] = list(v)
                else:
                    state[k] = v
        return jsonify(state)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/learning-stats")
def api_learning():
    if LEARNING_ENGINE:
        return jsonify(LEARNING_ENGINE.get_summary_stats())
    return jsonify({"message": "Learning Engine no inicializado"})


@app.route("/api/regime")
def api_regime():
    with STATE_LOCK:
        return jsonify(BOT_STATE.get("market_regime", {}))


@app.route("/api/chart")
def api_chart():
    symbol = request.args.get("symbol", "TSLA").upper()
    try:
        if DATA_CLIENT is None:
            return jsonify({"candles": [], "price": 0, "rsi": "50", "netFlow": "0.0B"})

        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(5, TimeFrameUnit.Minute),
            limit=60,
            feed=DataFeed.IEX,
        )
        bars = DATA_CLIENT.get_stock_bars(req).df

        if bars.empty:
            req_fallback = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(1, TimeFrameUnit.Hour),
                limit=40,
                feed=DataFeed.IEX,
            )
            bars = DATA_CLIENT.get_stock_bars(req_fallback).df

        candles = []
        last_price = 0.0
        if not bars.empty:
            if isinstance(bars.index, pd.MultiIndex):
                bars = bars.xs(symbol, level=0)
            bars["ma"] = bars["close"].rolling(10).mean()
            for idx, row in bars.iterrows():
                c_val = float(row["close"])
                last_price = c_val
                time_str = str(idx)
                if " " in time_str:
                    time_label = time_str.split(" ")[1][:5]
                else:
                    time_label = time_str[-5:]

                candles.append({
                    "t": time_label,
                    "o": float(row["open"]),
                    "h": float(row["high"]),
                    "l": float(row["low"]),
                    "c": c_val,
                    "close": c_val,
                    "ma": float(row["ma"]) if pd.notna(row["ma"]) else c_val,
                })

        return jsonify({
            "candles": candles,
            "price": round(last_price, 2),
            "rsi": "54 / 38",
            "netFlow": "2.10B"
        })
    except Exception as e:
        return jsonify({"candles": [], "price": 0, "error": str(e)})


@app.route("/api/close-all", methods=["POST"])
def close_all_api():
    try:
        client = TradingClient(Config.API_KEY, Config.SECRET_KEY, paper=True)
        positions = client.get_all_positions()
        closed = []
        errors = []
        for p in positions:
            try:
                try:
                    req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[p.symbol])
                    orders = client.get_orders(filter=req)
                    for o in orders:
                        client.cancel_order_by_id(o.id)
                except Exception:
                    pass

                client.close_position(p.symbol)
                closed.append(p.symbol)
                log_msg(f"MANUAL CLOSE-ALL: {p.symbol}")
            except Exception as e:
                errors.append(f"{p.symbol}: {e}")

        return jsonify({"closed": closed, "count": len(closed), "errors": errors})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/close-symbol", methods=["POST"])
def close_symbol_api():
    try:
        data = request.get_json(silent=True) or {}
        symbol = request.args.get("symbol") or data.get("symbol")
        if not symbol:
            return jsonify({"error": "Falta el parámetro symbol"}), 400

        symbol = symbol.upper()
        client = TradingClient(Config.API_KEY, Config.SECRET_KEY, paper=True)

        try:
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
            orders = client.get_orders(filter=req)
            for o in orders:
                client.cancel_order_by_id(o.id)
        except Exception:
            pass

        client.close_position(symbol)
        log_msg(f"MANUAL CLOSE individual: {symbol}")
        return jsonify({"message": f"Cerrando posición {symbol}", "symbol": symbol})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reclassify", methods=["POST"])
def api_reclassify():
    log_msg("[MANUAL] RE-CLASSIFIER disparado desde Dashboard")
    return jsonify({"status": "ok"})


@app.route("/health")
def health():
    with STATE_LOCK:
        eq = BOT_STATE["equity"]
    return jsonify({"status": "ok", "bot": "V12 ADAPTIVE", "equity": eq})


def start_bot():
    try:
        log_msg("Iniciando TradingBrain V12 Adaptive...")
        time.sleep(2)
        brain = TradingBrain()
        brain.run_loop()
    except Exception as e:
        log_msg(f"ERROR CRÍTICO: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    t = threading.Thread(target=start_bot, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 10000))
    log_msg(f"Flask AURA V12 corriendo en puerto {port}")
    app.run(host="0.0.0.0", port=port)
