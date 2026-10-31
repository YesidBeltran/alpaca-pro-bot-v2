"""
Gestor de Riesgo y Posición con Trailing Stop Dinámico y Breakeven
"""
class RiskManager:
    def __init__(self, config):
        self.risk_per_trade = getattr(config, "RISK_PER_TRADE", 0.0005)
        self.max_positions = getattr(config, "MAX_POSITIONS", 2)

    def calculate_position_size(self, equity, entry_price, stop_loss_price, dynamic_multiplier=1.0):
        """
        Calcula el tamaño seguro de la posición.
        Aplica el multiplicador dinámico del Learning Engine (0.0 a 1.3).
        """
        if entry_price <= 0 or dynamic_multiplier <= 0:
            return 0

        risk_amount = (equity * self.risk_per_trade) * dynamic_multiplier
        risk_per_share = abs(entry_price - stop_loss_price)

        min_risk = entry_price * 0.012  # Mínimo 1.2%
        if risk_per_share < min_risk:
            risk_per_share = min_risk

        if risk_per_share <= 0:
            return 0

        qty = int(risk_amount / risk_per_share)

        # Cap de liquidez por buying power (máx 20% del equity por operación)
        max_notional = equity * 0.20
        max_qty_by_power = int(max_notional / entry_price)
        qty = min(qty, max_qty_by_power)

        # Límites por precio de acción
        if entry_price > 300:
            qty = min(qty, 80)
        elif entry_price > 150:
            qty = min(qty, 150)
        else:
            qty = min(qty, 250)

        return max(qty, 0)

    def can_open_new_position(self, current_positions):
        return len(current_positions) < self.max_positions

    def get_stop_take(self, entry, direction, atr=None):
        atr_dist = atr * 1.8 if atr and atr > 0 else entry * 0.018
        min_dist = entry * 0.012
        if atr_dist < min_dist:
            atr_dist = min_dist

        if direction == "long":
            sl = entry - atr_dist
            tp = entry + (atr_dist * 2.2)
        else:
            sl = entry + atr_dist
            tp = entry - (atr_dist * 2.2)

        return round(sl, 2), round(tp, 2), round(atr_dist, 2)

    def evaluate_trailing_stop(self, entry_price, current_price, current_sl, direction, atr):
        """
        Gestión Activa:
        1. Breakeven: Si el trade avanza +1R a favor, sube el SL a precio de entrada (Riesgo Cero).
        2. Trailing Stop: Si avanza más de +1.5R, arrastra el SL a (Precio Máximo - 1.5 * ATR).
        Retorna (nuevo_sl, razon) o (None, None) si no requiere cambio.
        """
        atr_val = atr if atr and atr > 0 else (entry_price * 0.015)
        initial_risk = abs(entry_price - current_sl)

        if direction == "long":
            gain = current_price - entry_price
            # Breakeven a +1R
            if gain >= initial_risk and current_sl < entry_price:
                new_sl = round(entry_price + 0.02, 2)  # +$0.02 para absorber comisiones mínimas
                return new_sl, "BREAKEVEN (+1R alcanzado)"

            # Trailing stop por encima de 1.5R
            if gain >= initial_risk * 1.5:
                trailing_sl = round(current_price - (atr_val * 1.5), 2)
                if trailing_sl > current_sl:
                    return trailing_sl, "TRAILING STOP ATR"

        elif direction == "short":
            gain = entry_price - current_price
            if gain >= initial_risk and current_sl > entry_price:
                new_sl = round(entry_price - 0.02, 2)
                return new_sl, "BREAKEVEN (+1R alcanzado)"

            if gain >= initial_risk * 1.5:
                trailing_sl = round(current_price + (atr_val * 1.5), 2)
                if trailing_sl < current_sl:
                    return trailing_sl, "TRAILING STOP ATR"

        return None, None
