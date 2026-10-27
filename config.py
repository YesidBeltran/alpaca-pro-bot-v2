import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    API_KEY = os.getenv("APCA_API_KEY_ID")
    SECRET_KEY = os.getenv("APCA_API_SECRET_KEY")
    BASE_URL = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")
    
    SYMBOLS = [s.strip().upper() for s in os.getenv("SYMBOLS", "AAPL,SPY,QQQ").split(",")]
    TIMEFRAME = os.getenv("TIMEFRAME", "15Min")
    RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.005"))
    MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "3"))
    
    # Telegram
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    
    BACKTEST_MONTHS = int(os.getenv("BACKTEST_MONTHS", "6"))

    @classmethod
    def validate(cls):
        if not cls.API_KEY or not cls.SECRET_KEY:
            raise ValueError("Faltan API Keys de Alpaca. Revisa tu .env")
