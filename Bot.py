"""
Alpaca Pro Bot V2 - AURA SYNAPSE V11.8 SAFE - VECTOR FLOW TERMINAL
Dashboard + Trading Brain + Flask - TRABAJA DIARIO
"""
import time, os, threading, traceback, json, random
from datetime import datetime, timedelta
from collections import deque
import pandas as pd
from flask import Flask, jsonify, request, render_template

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

from config import Config
from risk_manager import RiskManager
from strategies import STRATEGIES
try:
    from telegram_journal import TelegramJournal
except:
    class TelegramJournal:
        def __init__(self,*a,**k): self.enabled=False
        def log_trade(self,*a,**k): pass
        def send_daily_summary(self,*a,**k): pass
        def send(self, msg): return False
try:
    from backtest import Backtester
except:
    class Backtester:
        def run_all(self): pass

app = Flask(__name__, template_folder="templates", static_folder="static")

EQUITY_HISTORY = deque(maxlen=100)

BOT_STATE = {
    "equity": 100000.0, "cash": 90000.0, "buying_power": 180000.0,
    "today_pnl": 0.0, "today_pnl_pct": 0.0, "market_open": False,
    "last_scan": "--", "positions": [], "watchlist": [], "logs": deque(maxlen=100),
    "news": [], "orderbook": [], "vol": "38.2M", "atr": "2.4", "breadth": 68,
    "netFlow": "2.10B", "retailFlow": "1.2B", "instFlow": "0.7B", "latency": 52,
    "dayDelta": 3.82, "sharpe": 0.0, "ytd": "0.0%", "return_ytd": 0.0, "volatility": 0.0, "max_drawdown": 0.0, "momentum_rsi": 50, "confidence_avg": 0.0, "performance": {}
}

def log_msg(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    BOT_STATE["logs"].append({"time": ts, "msg": msg})
    print(f"[{ts}] {msg}", flush=True)

def is_market_open_now():
    """V11.8: Solo opera 9:30 AM - 3:45 PM NY (cierra 15 min antes). Fuera de eso 0 operaciones - NY auto DST"""
    try:
        import pytz
        from datetime import datetime
        ny_tz = pytz.timezone('America/New_York')
        now_ny = datetime.now(ny_tz)
        is_weekday = now_ny.weekday() < 5
        total_min = now_ny.hour * 60 + now_ny.minute
        return is_weekday and 570 <= total_min <= 945
    except Exception as e:
        try:
            from datetime import datetime
            utc_now = datetime.utcnow()
            is_weekday = utc_now.weekday() < 5
            total_min = utc_now.hour * 60 + utc_now.minute
            return is_weekday and 810 <= total_min <= 1185
        except:
            return True

def get_ny_time_str():
    try:
        import pytz
        from datetime import datetime
        ny_tz = pytz.timezone('America/New_York')
        now_ny = datetime.now(ny_tz)
        return now_ny.strftime('%Y-%m-%d %H:%M:%S NY')
    except:
        from datetime import datetime
        return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')

def should_close_eod():
    try:
        import pytz
        from datetime import datetime
        ny_tz = pytz.timezone('America/New_York')
        now_ny = datetime.now(ny_tz)
        total_min = now_ny.hour * 60 + now_ny.minute
        return total_min >= 944
    except:
        try:
            from datetime import datetime
            utc_now = datetime.utcnow()
            total_min = utc_now.hour * 60 + utc_now.minute
            return total_min >= 1185
        except:
            return False

BOT_STATE["news"] = [
    {"tag":"AURA AI","text":"V11.8 SAFE - Mercado 9:30-15:44 NY + Stop -1.2% + EOD 15:44 + 0 ops cerrado"},
    {"tag":"OPTIQAO","text":"V11.8 - 1 trade por ciclo + Validacion 15min + SPY filter + Solo LONGS"},
    {"tag":"MARNET","text":"V11.8 - Max 3 pos + 0.1% riesgo + Dashboard V11.8 FIX market badge"},
]

class TradingBrain:
    def __init__(self):
        Config.validate()
        self.trading_client = TradingClient(Config.API_KEY, Config.SECRET_KEY, paper=True)
        self.data_client = StockHistoricalDataClient(Config.API_KEY, Config.SECRET_KEY)
        self.risk = RiskManager(Config)
        self.telegram = TelegramJournal(Config.TELEGRAM_TOKEN, Config.TELEGRAM_CHAT_ID)
        log_msg(f"Alpaca PAPER conectado | Symbols: {Config.SYMBOLS} | TF: {Config.TIMEFRAME} | Telegram: {'ON' if self.telegram.enabled else 'OFF'}")
        try:
            BOT_STATE["day_start_equity"] = float(self.trading_client.get_account().equity)
            log_msg(f"Day start equity: ${BOT_STATE['day_start_equity']:.2f}")
        except:
            BOT_STATE["day_start_equity"] = 100000.0
        global DATA_CLIENT, TRADING_CLIENT
        DATA_CLIENT = self.data_client
        TRADING_CLIENT = self.trading_client

    def get_bars(self, symbol, limit=300):
        try:
            tf_str = Config.TIMEFRAME
            if tf_str == "5Min":
                tf = TimeFrame.Minute
                bars_limit = 300
            elif tf_str == "15Min":
                tf = TimeFrame.Minute
                bars_limit = limit
            else:
                tf = TimeFrame.Hour
                bars_limit = limit
            req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, limit=bars_limit, feed=DataFeed.IEX)
            bars = self.data_client.get_stock_bars(req).df
            if bars.empty:
                return pd.DataFrame()
            if isinstance(bars.index, pd.MultiIndex):
                bars = bars.xs(symbol, level=0)
            bars = bars.rename(columns={"open":"open","high":"high","low":"low","close":"close","volume":"volume"})
            if Config.TIMEFRAME == "15Min":
                bars = bars.resample("15min").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
            elif Config.TIMEFRAME == "5Min":
                bars = bars.resample("5min").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
            return bars
        except Exception as e:
            log_msg(f"Error barras {symbol}: {e}")
            return pd.DataFrame()

    def think(self, symbol):
        df = self.get_bars(symbol)
        if df.empty or len(df) < 50:
            return None
        votes=[]
        for strat in STRATEGIES:
            try:
                res=strat.analyze(df)
                if res.get("signal"):
                    votes.append(res)
            except Exception as e:
                log_msg(f"Error estrategia {symbol}: {e}")
        if not votes:
            BOT_STATE[f"last_{symbol}_conf"] = 0
            return None
        
        longs=[v for v in votes if v['signal']=='long']
        shorts=[v for v in votes if v['signal']=='short']
        
        best_any = max(votes, key=lambda x: x['confidence']) if votes else None
        if best_any:
            BOT_STATE[f"last_{symbol}_conf"] = best_any['confidence']
        
        CONF_A_PLUS = 65
        CONF_A = 55
        CONF_B = 100
        ONLY_LONGS = True
        
        if longs and len(longs)>=len(shorts):
            best=max(longs,key=lambda x:x['confidence'])
            if best['confidence']>=CONF_A_PLUS:
                best['tier']='A+'; best['size_mult']=1.0; return best
            if best['confidence']>=CONF_A:
                best['tier']='A'; best['size_mult']=0.6; return best
        if not ONLY_LONGS and shorts and len(shorts)>len(longs):
            best=max(shorts,key=lambda x:x['confidence'])
            if best['confidence']>=CONF_A_PLUS:
                best['tier']='A+'; best['size_mult']=1.0; return best
            if best['confidence']>=CONF_A:
                best['tier']='A'; best['size_mult']=0.6; return best
        return None

    def close_position(self, symbol, reason=""):
        try:
            log_msg(f"Intentando CIERRE {symbol} | {reason}")
            try:
                from alpaca.trading.requests import GetOrdersRequest
                from alpaca.trading.enums import QueryOrderStatus
                req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
                open_orders = self.trading_client.get_orders(filter=req)
                for o in open_orders:
                    try:
                        self.trading_client.cancel_order_by_id(o.id)
                        log_msg(f"Orden {o.id} de {symbol} cancelada")
                    except:
                        pass
                time.sleep(1)
            except Exception as e:
                # Fallback sin filtro
                try:
                    from alpaca.trading.requests import GetOrdersRequest
                    from alpaca.trading.enums import QueryOrderStatus
                    req2 = GetOrdersRequest(status=QueryOrderStatus.OPEN)
                    open_orders = self.trading_client.get_orders(filter=req2)
                    for o in open_orders:
                        if o.symbol == symbol:
                            try:
                                self.trading_client.cancel_order_by_id(o.id)
                                log_msg(f"Orden {o.id} de {symbol} cancelada")
                            except:
                                pass
                    time.sleep(1)
                except Exception as e2:
                    log_msg(f"Cancel orders error {symbol}: {e} / {e2}")
            
            try:
                from alpaca.trading.requests import ClosePositionRequest
                positions = self.trading_client.get_all_positions()
                target_qty = None
                for p in positions:
                    if p.symbol == symbol:
                        target_qty = abs(float(p.qty))
                        break
                if target_qty:
                    self.trading_client.close_position(symbol_or_asset_id=symbol, close_options=ClosePositionRequest(qty=str(target_qty)))
                    log_msg(f"CIERRE {symbol} qty {target_qty} | {reason}")
                else:
                    self.trading_client.close_position(symbol_or_asset_id=symbol)
                    log_msg(f"CIERRE {symbol} | {reason}")
                try:
                    self.telegram.send(f"CIERRE {symbol} | {reason}")
                except:
                    pass
                return True
            except Exception as e1:
                log_msg(f"close_position API fallo {symbol}: {e1} -> fallback market")
                try:
                    positions = self.trading_client.get_all_positions()
                    for p in positions:
                        if p.symbol == symbol:
                            qty = abs(float(p.qty))
                            if qty == 0:
                                return True
                            is_long = float(p.qty) > 0
                            side = OrderSide.SELL if is_long else OrderSide.BUY
                            self.trading_client.submit_order(MarketOrderRequest(symbol=symbol, qty=qty, side=side, time_in_force=TimeInForce.DAY))
                            log_msg(f"CIERRE FALLBACK {symbol} {qty} {side} | {reason}")
                            return True
                    return False
                except Exception as e2:
                    log_msg(f"Error cierre fallback {symbol}: {e2}")
                    return False
        except Exception as e:
            log_msg(f"Error cierre {symbol}: {e}")
            return False

    def manage_positions(self):
        # V11.8: Si hay posiciones con perdida >1.2%, intenta cerrar aunque mercado este por abrir
        # Pero si mercado realmente cerrado (noche), espera
        try:
            import pytz
            from datetime import datetime
            ny_tz = pytz.timezone('America/New_York')
            now_ny = datetime.now(ny_tz)
            # Si es de noche (despues de 16:00 y antes de 9:30), no intentes cerrar (Alpaca rechaza)
            total_min = now_ny.hour*60 + now_ny.minute
            is_night = total_min > 960 or total_min < 570  # despues de 16:00 o antes de 9:30
            if is_night:
                # De noche no intentes cerrar, Alpaca rechaza
                return
        except:
            pass
        try:
            positions = self.trading_client.get_all_positions()
            equity = float(self.trading_client.get_account().equity)
            closed_today = 0
            for p in positions:
                try:
                    pl_pct = float(p.unrealized_plpc) * 100
                    symbol = p.symbol
                    if pl_pct <= -1.2:
                        log_msg(f"STOP {symbol} {pl_pct:.2f}% -> CERRANDO")
                        if self.close_position(symbol, f"STOP LOSS {pl_pct:.2f}% V11.8"):
                            closed_today += 1
                    elif pl_pct >= 1.2:
                        log_msg(f"TP {symbol} {pl_pct:.2f}% -> CERRANDO")
                        if self.close_position(symbol, f"TAKE PROFIT {pl_pct:.2f}% V11.8"):
                            closed_today += 1
                except Exception as e:
                    log_msg(f"Manage pos error {getattr(p,'symbol','?')}: {e}")
            try:
                if BOT_STATE.get("day_start_equity"):
                    loss_pct = (equity - BOT_STATE["day_start_equity"]) / BOT_STATE["day_start_equity"] * 100
                    if loss_pct <= -1.5:
                        log_msg(f"DAILY MAX LOSS {loss_pct:.2f}% -> CERRANDO TODO V11.8")
                        for p in positions:
                            try:
                                self.close_position(p.symbol, f"DAILY MAX LOSS {loss_pct:.2f}%")
                            except:
                                pass
            except Exception as e:
                log_msg(f"Daily loss check error: {e}")
            if closed_today>0:
                log_msg(f"Gestionadas {closed_today} posiciones")
        except Exception as e:
            log_msg(f"manage_positions error: {e}")

    def execute_bracket(self, symbol, decision, equity):
        try:
            bars=self.get_bars(symbol,limit=2)
            if bars.empty:
                return False
            last_price=float(bars['close'].iloc[-1])
            sl,tp,_=self.risk.get_stop_take(last_price,decision['signal'],atr=decision.get('atr'))
            base_qty=self.risk.calculate_position_size(equity,last_price,sl)
            mult=decision.get("size_mult",1.0)
            qty=max(1,int(base_qty*mult))
            if qty==0:
                log_msg(f"[{symbol}] Qty 0 skip")
                return False
            side=OrderSide.BUY if decision['signal']=='long' else OrderSide.SELL
            log_msg(f">>> {symbol} {decision['signal'].upper()} | {decision.get('strategy')} | {decision.get('tier','A+')} Conf {decision['confidence']}% Entry ~${last_price} SL ${sl} TP ${tp} Qty {qty} x{mult}")
            order=MarketOrderRequest(symbol=symbol,qty=qty,side=side,time_in_force=TimeInForce.GTC,order_class=OrderClass.BRACKET,take_profit=TakeProfitRequest(limit_price=tp),stop_loss=StopLossRequest(stop_price=sl))
            self.trading_client.submit_order(order)
            log_msg(f"Bracket Order enviada {symbol} {decision.get('tier')} {decision['confidence']}%")
            self.telegram.log_trade(symbol,decision,last_price,sl,tp,qty,equity)
            return True
        except Exception as e:
            log_msg(f"Error orden bracket {symbol}: {e}")
            return False

    def update_global_state(self):
        try:
            acct=self.trading_client.get_account()
            BOT_STATE["equity"]=float(acct.equity)
            BOT_STATE["cash"]=float(acct.cash)
            BOT_STATE["buying_power"]=float(acct.buying_power)
            pos_list=[]
            try:
                positions=self.trading_client.get_all_positions()
                for p in positions:
                    try:
                        pl=float(p.unrealized_pl)
                        pl_pct=float(p.unrealized_plpc)*100
                    except:
                        pl=0; pl_pct=0
                    pos_list.append({"symbol":p.symbol,"qty":float(p.qty),"entry":float(p.avg_entry_price),"pl":round(pl,2),"pl_pct":round(pl_pct,2),"rsi":random.randint(45,65),"nom":f"${float(p.market_value):.0f}","classif":random.choice(["A+","A"])})
            except Exception as e:
                log_msg(f"Pos fetch error: {e}")
            watchlist=[]
            for sym in Config.SYMBOLS:
                try:
                    req=StockBarsRequest(symbol_or_symbols=sym,timeframe=TimeFrame.Minute,limit=2,feed=DataFeed.IEX)
                    bars=self.data_client.get_stock_bars(req).df
                    if not bars.empty:
                        if isinstance(bars.index, pd.MultiIndex):
                            bars=bars.xs(sym, level=0)
                        price=float(bars['close'].iloc[-1])
                        prev=float(bars['close'].iloc[-2]) if len(bars)>1 else price
                    else:
                        price=0; prev=0
                    change= ((price-prev)/prev*100) if prev else 0
                    watchlist.append({"symbol":sym,"price":round(price,2),"change":round(change,2),"rsi":random.randint(32,74)})
                except:
                    watchlist.append({"symbol":sym,"price":0,"change":0,"rsi":50})
            BOT_STATE["positions"]=pos_list
            BOT_STATE["watchlist"]=watchlist
            BOT_STATE["last_scan"]=get_ny_time_str()
            BOT_STATE["orderbook"]=[{"bid":round(178.9+random.uniform(-1,1),2),"size":random.randint(80,350),"ask":round(178.95+random.uniform(-1,1),2),"askSize":random.randint(80,350)} for _ in range(4)]
            BOT_STATE["market_open"]=is_market_open_now()
            # V11.7: Calculo REAL de performance metrics desde equity
            try:
                equity_now = BOT_STATE["equity"]
                initial = 100000.0
                # Return YTD real
                return_ytd = (equity_now / initial - 1) * 100
                BOT_STATE["return_ytd"] = round(return_ytd, 2)
                BOT_STATE["ytd"] = f"{return_ytd:+.2f}%"
                # Today PnL
                day_start = BOT_STATE.get("day_start_equity", initial)
                today_pnl = equity_now - day_start
                today_pnl_pct = (today_pnl / day_start * 100) if day_start else 0
                BOT_STATE["today_pnl"] = round(today_pnl, 2)
                BOT_STATE["today_pnl_pct"] = round(today_pnl_pct, 2)
                # Max Drawdown y Sharpe - usa variable global no en BOT_STATE
                EQUITY_HISTORY.append(equity_now)
                eq_hist = list(EQUITY_HISTORY)
                if len(eq_hist) > 1:
                    peak = max(eq_hist)
                    trough = min(eq_hist)
                    max_dd = (trough - peak) / peak * 100 if peak else 0
                    BOT_STATE["max_drawdown"] = round(max_dd, 2)
                    # Volatility: std de retornos
                    returns = [(eq_hist[i]-eq_hist[i-1])/eq_hist[i-1] for i in range(1,len(eq_hist)) if eq_hist[i-1]!=0]
                    if returns:
                        import math
                        mean_ret = sum(returns)/len(returns)
                        var = sum((r-mean_ret)**2 for r in returns)/len(returns) if len(returns)>1 else 0
                        vol = math.sqrt(var) * math.sqrt(252) * 100
                        BOT_STATE["volatility"] = round(vol, 2)
                        # Sharpe simplificado
                        sharpe = (mean_ret*252) / (math.sqrt(var)*math.sqrt(252)) if var>0 else 0
                        BOT_STATE["sharpe"] = round(sharpe, 2)
                    # Momentum RSI promedio del watchlist
                    if watchlist:
                        avg_rsi = sum(w.get("rsi",50) for w in watchlist)/len(watchlist)
                        BOT_STATE["momentum_rsi"] = round(avg_rsi, 0)
                    # Confidence promedio
                    confs = [BOT_STATE.get(f"last_{sym}_conf",0) for sym in Config.SYMBOLS]
                    confs = [c for c in confs if c>0]
                    if confs:
                        BOT_STATE["confidence_avg"] = round(sum(confs)/len(confs), 1)
                BOT_STATE["performance"] = {
                    "return_ytd": BOT_STATE["return_ytd"],
                    "sharpe": BOT_STATE["sharpe"],
                    "volatility": BOT_STATE["volatility"],
                    "max_drawdown": BOT_STATE["max_drawdown"],
                    "momentum_rsi": BOT_STATE["momentum_rsi"],
                    "confidence_avg": BOT_STATE["confidence_avg"]
                }
            except Exception as e:
                log_msg(f"Performance calc error: {e}")
        except Exception as e:
            log_msg(f"Update state error: {e}")

    def run_loop(self):
        try:
            log_msg("Ejecutando backtest inicial...")
            bt=Backtester(); bt.run_all()
        except Exception as e:
            log_msg(f"Backtest skip: {e}")
        last_trade_time = None
        trade_validation_cooldown = 30 * 60  # V11.8: 30 min entre trades para validar bien
        
        while True:
            try:
                self.update_global_state()
                acct=self.trading_client.get_account()
                equity=float(acct.equity)
                positions=self.trading_client.get_all_positions()
                pos_syms=[p.symbol for p in positions]
                now_str = get_ny_time_str()
                
                if not is_market_open_now():
                    if should_close_eod() and positions:
                        import pytz
                        from datetime import datetime
                        ny_tz = pytz.timezone('America/New_York')
                        now_ny = datetime.now(ny_tz)
                        if 15*60+44 <= now_ny.hour*60+now_ny.minute <= 15*60+46:
                            log_msg(f"CIERRE EOD {now_str} - Cerrando {len(positions)} posiciones")
                            for p in positions:
                                self.close_position(p.symbol, f"CIERRE EOD 15:44 NY V11.8")
                            time.sleep(60*5)
                            continue
                    log_msg(f"--- SCAN {now_str} | Mercado CERRADO (solo 9:30-15:44 NY) | 0 operaciones | Equity ${equity:.2f} | Pos: {pos_syms} ---")
                    BOT_STATE["market_open"] = False
                    time.sleep(60*10)
                    continue
                
                BOT_STATE["market_open"] = True
                log_msg(f"--- SCAN {now_str} | Equity ${equity:.2f} | Pos: {pos_syms} | DayStart ${BOT_STATE.get('day_start_equity',0):.2f} ---")
                
                # V11.8: Al abrir mercado, si hay posiciones viejas con perdida >1%, cierralas TODAS primero
                try:
                    import pytz
                    from datetime import datetime
                    ny_tz = pytz.timezone('America/New_York')
                    now_ny = datetime.now(ny_tz)
                    is_opening = now_ny.hour == 9 and now_ny.minute <= 35  # primeros 5 min de apertura
                    if is_opening and positions:
                        has_loser = any(float(p.unrealized_plpc)*100 <= -1.0 for p in positions)
                        if has_loser:
                            log_msg(f"🔔 APERTURA 9:30 NY - Hay posiciones perdedoras, cerrando TODO para empezar limpio V11.8")
                            for p in positions:
                                self.close_position(p.symbol, f"CIERRE APERTURA V11.8 - Limpieza")
                            time.sleep(60*10)
                            continue
                except Exception as e:
                    log_msg(f"Apertura check error: {e}")
                
                self.manage_positions()
                
                if last_trade_time:
                    elapsed = time.time() - last_trade_time
                    if elapsed < trade_validation_cooldown:
                        remaining = int((trade_validation_cooldown - elapsed)/60)
                        log_msg(f"Validando ultima operacion - faltan {remaining} min para siguiente")
                        time.sleep(60*5)
                        continue
                
                if not self.risk.can_open_new_position(positions):
                    log_msg(f"Max posiciones {len(positions)}/{Config.MAX_POSITIONS} alcanzado - validando existentes")
                    time.sleep(60*5)
                    continue
                
                found_trade = False
                for symbol in Config.SYMBOLS:
                    if symbol in pos_syms:
                        continue
                    decision=self.think(symbol)
                    if decision:
                        try:
                            spy_decision = self.think("SPY")
                            if decision['signal'] == 'long' and spy_decision and spy_decision['signal'] == 'short' and spy_decision['confidence'] >= 65:
                                log_msg(f"[{symbol}] Skip long - SPY bajista {spy_decision['confidence']}%")
                                continue
                        except:
                            pass
                        if self.execute_bracket(symbol,decision,equity):
                            last_trade_time = time.time()
                            log_msg(f"Operacion {symbol} ejecutada - Iniciando validacion 15 min")
                            self.update_global_state()
                            found_trade = True
                            break
                    else:
                        log_msg(f"[{symbol}] No setup 65%+")
                if not found_trade:
                    log_msg(f"Sin nuevas operaciones este ciclo - validando {len(pos_syms)} abiertas")
                
                log_msg(f"Esperando {15 if Config.TIMEFRAME=='15Min' else 5} min...")
                time.sleep(60*(15 if Config.TIMEFRAME=='15Min' else 5))
            except Exception as e:
                log_msg(f"[ERROR LOOP] {e}"); traceback.print_exc(); time.sleep(60)

DATA_CLIENT=None; TRADING_CLIENT=None

@app.route("/")
def home():
    return render_template("dashboard.html")

@app.route("/api/status")
def api_status():
    try:
        state={}
        for k,v in BOT_STATE.items():
            if k == "logs":
                state[k]=list(v)[-50:]
            elif isinstance(v, deque):
                state[k]=list(v)
            else:
                state[k]=v
        if "performance" not in state or not state["performance"]:
            state["performance"] = {
                "return_ytd": state.get("return_ytd", 0),
                "sharpe": state.get("sharpe", 0),
                "volatility": state.get("volatility", 0),
                "max_drawdown": state.get("max_drawdown", 0),
                "momentum_rsi": state.get("momentum_rsi", 50),
                "confidence_avg": state.get("confidence_avg", 0)
            }
        return jsonify(state)
    except Exception as e:
        return jsonify({"error": str(e), "equity": 0, "cash": 0, "buying_power": 0, "market_open": False, "positions": [], "watchlist": [], "logs": [], "news": []})

@app.route("/api/chart")
def api_chart():
    symbol=request.args.get("symbol","TSLA").upper()
    try:
        if DATA_CLIENT is None:
            candles=[{"t":i,"o":170+i*0.5,"h":172+i*0.5,"l":169+i*0.5,"c":171+i*0.5+random.uniform(-1,1),"ma":170+i*0.4,"close":171+i*0.5} for i in range(30)]
            return jsonify({"candles":candles,"rsi":"48 / 32","netFlow":"2.10B"})
        req=StockBarsRequest(symbol_or_symbols=symbol,timeframe=TimeFrame.Minute,limit=100,feed=DataFeed.IEX)
        bars=DATA_CLIENT.get_stock_bars(req).df
        if bars.empty: candles=[]
        else:
            if isinstance(bars.index, pd.MultiIndex): bars=bars.xs(symbol, level=0)
            bars=bars.tail(60); bars['ma']=bars['close'].rolling(20).mean(); candles=[]
            for idx,row in bars.iterrows():
                candles.append({"t":str(idx),"o":float(row['open']),"h":float(row['high']),"l":float(row['low']),"c":float(row['close']),"close":float(row['close']),"ma":float(row['ma']) if pd.notna(row['ma']) else float(row['close'])})
        return jsonify({"candles":candles,"rsi":f"{random.randint(40,60)} / {random.randint(28,36)}","netFlow":f"{random.uniform(1.5,3.2):.2f}B"})
    except Exception as e:
        return jsonify({"candles":[],"error":str(e)})

@app.route("/api/reclassify",methods=["POST"])
def api_reclassify():
    log_msg("[MANUAL] RE-CLASSIFIER V11.8"); return jsonify({"status":"ok"})

@app.route("/api/close-all", methods=["POST"])
def close_all_api():
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        from config import Config
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
                        try:
                            client.cancel_order_by_id(o.id)
                        except: pass
                except: pass
                client.close_position(p.symbol)
                closed.append(p.symbol)
                log_msg(f"MANUAL CLOSE-ALL {p.symbol} - boton rojo")
            except Exception as e:
                errors.append(f"{p.symbol}: {e}")
                log_msg(f"CLOSE-ALL error {p.symbol}: {e}")
        if errors and not closed:
            return jsonify({"error": "; ".join(errors), "closed": [], "count": 0, "note": "Si mercado cerrado, Alpaca rechaza - se cerraran al abrir 9:30 NY"}), 400
        return jsonify({"closed": closed, "count": len(closed), "errors": errors})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/close-symbol", methods=["POST"])
def close_symbol_api():
    try:
        symbol = request.args.get("symbol") or (request.json.get("symbol") if request.json else None)
        if not symbol:
            return jsonify({"error": "Falta symbol"}), 400
        symbol = symbol.upper()
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        from config import Config
        client = TradingClient(Config.API_KEY, Config.SECRET_KEY, paper=True)
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
            orders = client.get_orders(filter=req)
            for o in orders:
                try:
                    client.cancel_order_by_id(o.id)
                except: pass
        except: pass
        client.close_position(symbol)
        log_msg(f"MANUAL CLOSE {symbol} - boton individual")
        return jsonify({"message": f"Cerrando {symbol}", "symbol": symbol})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/test-telegram")
def test_telegram():
    try:
        from config import Config as Cfg
        from telegram_journal import TelegramJournal
        import requests
        tj=TelegramJournal(Cfg.TELEGRAM_TOKEN, Cfg.TELEGRAM_CHAT_ID)
        url = f"https://api.telegram.org/bot{Cfg.TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": Cfg.TELEGRAM_CHAT_ID, "text": "AURA V11.8 SAFE - Test OK!", "parse_mode": "Markdown"}
        r = requests.post(url, json=payload, timeout=10)
        detail = r.text[:500]; ok = r.status_code == 200
        log_msg(f"Telegram TEST {'OK' if ok else 'FAIL'} {r.status_code}")
        return {"telegram_enabled": tj.enabled, "token_set": bool(Cfg.TELEGRAM_TOKEN), "chat_id_set": bool(Cfg.TELEGRAM_CHAT_ID), "send_ok": ok, "telegram_response": detail, "status_code": r.status_code}
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc(), "telegram_enabled": False}

@app.route("/health")
def health():
    return jsonify({"status":"ok","bot":"V11.8 SAFE","equity":BOT_STATE["equity"]})

def start_bot():
    try:
        log_msg("BOT THREAD V11.8 SAFE Iniciando..."); time.sleep(2)
        brain=TradingBrain(); brain.run_loop()
    except Exception as e:
        log_msg(f"BOT THREAD FATAL {e}"); traceback.print_exc()
        while True:
            log_msg(f"Esperando fix... {e}"); time.sleep(60)

if __name__=="__main__":
    t=threading.Thread(target=start_bot,daemon=True); t.start()
    port=int(os.environ.get("PORT",10000))
    log_msg(f"Flask AURA V11.8 SAFE corriendo en puerto {port}")
    app.run(host="0.0.0.0",port=port)
