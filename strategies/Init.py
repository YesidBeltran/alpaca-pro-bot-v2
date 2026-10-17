import importlib
STRATEGIES = []
for name in ["trend_pullback", "breakout", "smc"]:
    try:
        mod = importlib.import_module(f"strategies.{name}")
        STRATEGIES.append(mod)
    except Exception as e:
        print(f"[WARN] No se pudo cargar estrategia {name}: {e}")
