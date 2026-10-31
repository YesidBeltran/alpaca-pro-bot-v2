import json
import os
from datetime import datetime
import requests


class TelegramJournal:
    def __init__(self, token=None, chat_id=None, log_file="journal.json"):
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(
            token
            and chat_id
            and len(str(token)) > 20
            and not str(token).startswith("123")
        )
        self.log_file = log_file

    def send(self, message: str) -> bool:
        if not self.enabled:
            print(f"[Telegram desactivado] {message[:100]}...")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                print("[Telegram] Mensaje enviado")
                return True
            else:
                retry_payload = {"chat_id": self.chat_id, "text": message}
                r_retry = requests.post(url, json=retry_payload, timeout=10)
                if r_retry.status_code == 200:
                    return True
                print(f"[Telegram Error] {r.text}")
                return False
        except Exception as e:
            print(f"[Telegram Exception] {e}")
            return False

    def log_trade(self, symbol, decision, entry, sl, tp, qty, equity):
        entry_data = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "side": decision.get("signal", ""),
            "strategy": decision.get("strategy", ""),
            "confidence": decision.get("confidence", 0),
            "reason": decision.get("reason", ""),
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "qty": qty,
            "equity": equity,
        }

        logs = []
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    logs = json.load(f)
                    if not isinstance(logs, list):
                        logs = []
            except Exception as e:
                print(f"[Journal Warning] Error leyendo {self.log_file}: {e}")
                logs = []

        logs.append(entry_data)
        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2)
        except Exception as e:
            print(f"[Journal Error] Fallo al escribir {self.log_file}: {e}")

        strategy = decision.get("strategy", "N/A")
        reason = decision.get("reason", "N/A")
        signal = str(decision.get("signal", "TRADE")).upper()
        confidence = decision.get("confidence", 0)

        msg = f"""🚀 *NUEVO TRADE - Alpaca Pro Bot V12*
📊 {symbol} | {signal} | {strategy}
💡 {reason}
🎯 Entrada: ${entry:.2f} | Qty: {qty}
🛑 SL: ${sl:.2f} | ✅ TP: ${tp:.2f}
📈 Confianza: {confidence}% | Equity: ${equity:.2f}
"""
        self.send(msg)

    def send_daily_summary(self, trading_client):
        try:
            account = trading_client.get_account()
            positions = trading_client.get_all_positions()
            equity = float(account.equity)
            last_equity = float(account.last_equity) if getattr(account, "last_equity", None) else equity
            pnl = equity - last_equity

            pos_text = (
                "\n".join(
                    [
                        f"- {p.symbol}: {p.qty} @ ${float(p.avg_entry_price):.2f} PnL ${float(p.unrealized_pl):.2f}"
                        for p in positions
                    ]
                )
                if positions
                else "Sin posiciones abiertas"
            )

            msg = f"""📊 *RESUMEN DIARIO - Alpaca Pro Bot V12*
🕒 {datetime.now().strftime('%Y-%m-%d %H:%M')}
💰 Equity: ${equity:.2f} | PnL Hoy: ${pnl:.2f}
📦 Posiciones:
{pos_text}
🤖 Bot activo y aprendiendo...
"""
            self.send(msg)
        except Exception as e:
            print(f"Error resumen diario: {e}")
