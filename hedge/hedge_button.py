"""
One-click hedge tool for MetaTrader 5.

A small always-on-top window with two buttons:
  SIGNAL BUY  -> opens a SELL hedge (opposite side) with SL/TP attached
  SIGNAL SELL -> opens a BUY hedge (opposite side) with SL/TP attached
  CLOSE HEDGE -> closes every position this tool opened on the symbol

Requires: Python 3.11+, `pip install MetaTrader5`, and a running,
logged-in MT5 terminal with "Allow automated trading" enabled.
"""

import tkinter as tk
from tkinter import messagebox

# ================= CONFIG — EDIT THESE 4 LINES =================
SYMBOL    = "XAUUSDb"   # EXACT gold symbol name from MT5 Market Watch
LOT       = 0.30        # trade size in lots
SL_POINTS = 550         # stop-loss distance, in points
TP_POINTS = 670         # take-profit distance, in points
# ===============================================================

MAGIC     = 909090          # tag so CLOSE HEDGE only touches our own trades
COMMENT   = "hedge-button"
DEVIATION = 30              # max slippage in points

root = tk.Tk()
root.withdraw()  # hide until we know MT5 imports cleanly

try:
    import MetaTrader5 as mt5
except ImportError:
    messagebox.showerror(
        "Missing library",
        "The MetaTrader5 library is not installed.\n\n"
        "Open Command Prompt and run:\n\n"
        "    pip install MetaTrader5\n\n"
        "(or:  py -m pip install MetaTrader5 )",
    )
    raise SystemExit(1)


def ensure_connected():
    """Connect to the running MT5 terminal and make the symbol visible."""
    if mt5.terminal_info() is None:
        if not mt5.initialize():
            return None, f"Cannot connect to MT5 (error {mt5.last_error()}). Is the terminal running and logged in?"
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return None, f'Symbol "{SYMBOL}" not found. Check the exact name in Market Watch.'
    if not info.visible:
        if not mt5.symbol_select(SYMBOL, True):
            return None, f'Could not add "{SYMBOL}" to Market Watch.'
        info = mt5.symbol_info(SYMBOL)
    return info, None


def send_order(request):
    """Send an order, retrying with each filling mode the broker may require."""
    for filling in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
        request["type_filling"] = filling
        result = mt5.order_send(request)
        if result is None:
            return None
        if result.retcode != mt5.TRADE_RETCODE_INVALID_FILL:
            return result
    return result


def open_hedge(signal_is_buy):
    info, err = ensure_connected()
    if err:
        set_status(err, error=True)
        return

    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        set_status("No price data — is the market open?", error=True)
        return

    point = info.point
    if signal_is_buy:
        # Signal says BUY -> we hedge with a SELL at the bid.
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
        sl = price + SL_POINTS * point
        tp = price - TP_POINTS * point
        side = "SELL"
    else:
        # Signal says SELL -> we hedge with a BUY at the ask.
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
        sl = price - SL_POINTS * point
        tp = price + TP_POINTS * point
        side = "BUY"

    digits = info.digits
    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SYMBOL,
        "volume":       LOT,
        "type":         order_type,
        "price":        round(price, digits),
        "sl":           round(sl, digits),
        "tp":           round(tp, digits),
        "deviation":    DEVIATION,
        "magic":        MAGIC,
        "comment":      COMMENT,
        "type_time":    mt5.ORDER_TIME_GTC,
    }

    result = send_order(request)
    if result is None:
        set_status(f"Order failed: {mt5.last_error()}", error=True)
    elif result.retcode == mt5.TRADE_RETCODE_DONE:
        set_status(
            f"{side} {LOT} {SYMBOL} @ {result.price:.{digits}f}  "
            f"SL {sl:.{digits}f}  TP {tp:.{digits}f}"
        )
    else:
        set_status(f"Rejected ({result.retcode}): {result.comment}", error=True)


def close_hedges():
    info, err = ensure_connected()
    if err:
        set_status(err, error=True)
        return

    positions = mt5.positions_get(symbol=SYMBOL) or []
    ours = [p for p in positions if p.magic == MAGIC]
    if not ours:
        set_status("No hedge positions to close.")
        return

    digits = info.digits
    closed, failed = 0, 0
    for pos in ours:
        tick = mt5.symbol_info_tick(SYMBOL)
        if pos.type == mt5.POSITION_TYPE_SELL:
            close_type, price = mt5.ORDER_TYPE_BUY, tick.ask
        else:
            close_type, price = mt5.ORDER_TYPE_SELL, tick.bid
        request = {
            "action":    mt5.TRADE_ACTION_DEAL,
            "symbol":    SYMBOL,
            "volume":    pos.volume,
            "type":      close_type,
            "position":  pos.ticket,
            "price":     round(price, digits),
            "deviation": DEVIATION,
            "magic":     MAGIC,
            "comment":   COMMENT + "-close",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        result = send_order(request)
        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
        else:
            failed += 1

    if failed:
        set_status(f"Closed {closed}, FAILED {failed} — check MT5!", error=True)
    else:
        set_status(f"Closed {closed} hedge position(s). Flat.")


# ---------------------------- UI ----------------------------

def set_status(text, error=False):
    status.config(text=text, fg=("#c62828" if error else "#1b5e20"))
    root.update_idletasks()


root.deiconify()
root.title("Hedge")
root.attributes("-topmost", True)
root.resizable(False, False)

frame = tk.Frame(root, padx=12, pady=12)
frame.pack()

tk.Button(
    frame, text="SIGNAL BUY", command=lambda: open_hedge(True),
    bg="#2e7d32", fg="white", activebackground="#1b5e20", activeforeground="white",
    font=("Segoe UI", 16, "bold"), width=14, height=2,
).grid(row=0, column=0, padx=6, pady=4)

tk.Button(
    frame, text="SIGNAL SELL", command=lambda: open_hedge(False),
    bg="#c62828", fg="white", activebackground="#8e0000", activeforeground="white",
    font=("Segoe UI", 16, "bold"), width=14, height=2,
).grid(row=0, column=1, padx=6, pady=4)

tk.Button(
    frame, text="CLOSE HEDGE", command=close_hedges,
    bg="#455a64", fg="white", activebackground="#263238", activeforeground="white",
    font=("Segoe UI", 12, "bold"), width=32, height=1,
).grid(row=1, column=0, columnspan=2, padx=6, pady=(8, 4))

status = tk.Label(frame, text="Ready", font=("Segoe UI", 10), fg="#1b5e20", wraplength=380, justify="left")
status.grid(row=2, column=0, columnspan=2, pady=(8, 0))

info, err = ensure_connected()
if err:
    set_status(err, error=True)
else:
    set_status(f"Ready — {SYMBOL}, lot {LOT}, SL {SL_POINTS} / TP {TP_POINTS} points")

root.mainloop()
