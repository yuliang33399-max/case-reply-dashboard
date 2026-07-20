"""
One-click hedge tool for MetaTrader 5, with Tradovate click-link.

Manual mode (always available):
  SIGNAL BUY  -> opens a SELL hedge (opposite side) with SL/TP attached
  SIGNAL SELL -> opens a BUY hedge (opposite side) with SL/TP attached
  CLOSE HEDGE -> closes every position this tool opened on the symbol

Auto mode (Tradovate click-link, needs `pip install pynput`):
  1. Click SET BUY ZONE, hover the mouse over Tradovate's BUY button,
     wait for the 5-second countdown. Repeat with SET SELL ZONE.
  2. Switch AUTO-HEDGE to ON.
  3. Now your normal click on Tradovate's BUY button ALSO fires the
     hedge (opens a SELL in MT5), and the SELL button fires a BUY hedge.
     One click, both platforms.

Requires: Python 3.11+, `pip install MetaTrader5 pynput`, and a running,
logged-in MT5 terminal with "Allow automated trading" enabled.
"""

import json
import os
import time
import tkinter as tk
from tkinter import messagebox

# ================= CONFIG — EDIT THESE 4 LINES =================
SYMBOL    = "XAUUSDb"   # EXACT gold symbol name from MT5 Market Watch
LOT       = 0.30        # trade size in lots
SL_POINTS = 550         # stop-loss distance, in points
TP_POINTS = 670         # take-profit distance, in points
# ===============================================================

MAGIC       = 909090        # tag so CLOSE HEDGE only touches our own trades
COMMENT     = "hedge-button"
DEVIATION   = 30            # max slippage in points
ZONE_RADIUS = 45            # pixels around the saved spot that count as "on the button"
COOLDOWN_S  = 3             # ignore repeat clicks in the same zone for this many seconds

ZONES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hedge_zones.json")

root = tk.Tk()
root.withdraw()  # hide until we know MT5 imports cleanly

try:
    import MetaTrader5 as mt5
except ImportError:
    messagebox.showerror(
        "Missing library",
        "The MetaTrader5 library is not installed.\n\n"
        "Open Command Prompt and run:\n\n"
        "    py -m pip install MetaTrader5",
    )
    raise SystemExit(1)

try:
    from pynput import mouse as pynput_mouse
except ImportError:
    pynput_mouse = None  # manual buttons still work; auto mode disabled


# ---------------------------- MT5 ----------------------------

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


def open_hedge(signal_is_buy, source="manual"):
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

    prefix = "AUTO: " if source == "auto" else ""
    result = send_order(request)
    if result is None:
        set_status(f"{prefix}Order failed: {mt5.last_error()}", error=True)
    elif result.retcode == mt5.TRADE_RETCODE_DONE:
        set_status(
            f"{prefix}{side} {LOT} {SYMBOL} @ {result.price:.{digits}f}  "
            f"SL {sl:.{digits}f}  TP {tp:.{digits}f}"
        )
    else:
        set_status(f"{prefix}Rejected ({result.retcode}): {result.comment}", error=True)


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


# ----------------------- Tradovate link -----------------------

zones = {"buy": None, "sell": None}   # {"buy": [x, y], "sell": [x, y]}
auto_on = False
_last_fire = 0.0
_capturing = False


def load_zones():
    try:
        with open(ZONES_FILE, "r") as f:
            data = json.load(f)
        for k in ("buy", "sell"):
            if isinstance(data.get(k), list) and len(data[k]) == 2:
                zones[k] = [int(data[k][0]), int(data[k][1])]
    except (OSError, ValueError):
        pass


def save_zones():
    try:
        with open(ZONES_FILE, "w") as f:
            json.dump(zones, f)
    except OSError:
        pass


def capture_zone(kind):
    global _capturing
    if pynput_mouse is None:
        set_status("Auto mode needs pynput. Run:  py -m pip install pynput  then relaunch.", error=True)
        return
    if _capturing:
        return
    _capturing = True
    _countdown(kind, 5)


def _countdown(kind, n):
    global _capturing
    if n > 0:
        set_status(f"Hover the mouse over the Tradovate {kind.upper()} button — capturing in {n}...")
        root.after(1000, lambda: _countdown(kind, n - 1))
    else:
        x, y = pynput_mouse.Controller().position
        zones[kind] = [int(x), int(y)]
        save_zones()
        _capturing = False
        update_zone_label()
        set_status(f"{kind.upper()} zone saved at ({int(x)}, {int(y)}). Don't move/resize the Tradovate window now.")


def toggle_auto():
    global auto_on
    if pynput_mouse is None:
        set_status("Auto mode needs pynput. Run:  py -m pip install pynput  then relaunch.", error=True)
        return
    if not auto_on and zones["buy"] is None and zones["sell"] is None:
        set_status("Set the BUY/SELL zones first (SET BUY ZONE, then hover over Tradovate's button).", error=True)
        return
    auto_on = not auto_on
    if auto_on:
        auto_btn.config(text="AUTO-HEDGE: ON", bg="#e65100", activebackground="#bf360c")
        set_status("AUTO ON — your click on the Tradovate button will also fire the hedge.")
    else:
        auto_btn.config(text="AUTO-HEDGE: OFF", bg="#616161", activebackground="#424242")
        set_status("AUTO OFF — clicks on Tradovate do nothing here.")


def _in_zone(x, y, zone):
    return zone is not None and abs(x - zone[0]) <= ZONE_RADIUS and abs(y - zone[1]) <= ZONE_RADIUS


def _on_global_click(x, y, button, pressed):
    """Runs on pynput's listener thread — hand real work to the tk thread."""
    global _last_fire
    if not pressed or button != pynput_mouse.Button.left:
        return
    if not auto_on or _capturing:
        return
    now = time.monotonic()
    if now - _last_fire < COOLDOWN_S:
        return
    if _in_zone(x, y, zones["buy"]):
        _last_fire = now
        root.after(0, lambda: open_hedge(True, source="auto"))
    elif _in_zone(x, y, zones["sell"]):
        _last_fire = now
        root.after(0, lambda: open_hedge(False, source="auto"))


# ---------------------------- UI ----------------------------

def set_status(text, error=False):
    status.config(text=text, fg=("#c62828" if error else "#1b5e20"))
    root.update_idletasks()


def update_zone_label():
    parts = []
    parts.append(f"BUY zone: {'set' if zones['buy'] else '—'}")
    parts.append(f"SELL zone: {'set' if zones['sell'] else '—'}")
    zone_label.config(text="   ".join(parts))


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
).grid(row=1, column=0, columnspan=2, padx=6, pady=(8, 2))

tk.Button(
    frame, text="SET BUY ZONE", command=lambda: capture_zone("buy"),
    bg="#a5d6a7", font=("Segoe UI", 10, "bold"), width=14,
).grid(row=2, column=0, padx=6, pady=(10, 2))

tk.Button(
    frame, text="SET SELL ZONE", command=lambda: capture_zone("sell"),
    bg="#ef9a9a", font=("Segoe UI", 10, "bold"), width=14,
).grid(row=2, column=1, padx=6, pady=(10, 2))

auto_btn = tk.Button(
    frame, text="AUTO-HEDGE: OFF", command=toggle_auto,
    bg="#616161", fg="white", activebackground="#424242", activeforeground="white",
    font=("Segoe UI", 12, "bold"), width=32,
)
auto_btn.grid(row=3, column=0, columnspan=2, padx=6, pady=2)

zone_label = tk.Label(frame, text="", font=("Segoe UI", 9), fg="#555555")
zone_label.grid(row=4, column=0, columnspan=2)

status = tk.Label(frame, text="Ready", font=("Segoe UI", 10), fg="#1b5e20", wraplength=380, justify="left")
status.grid(row=5, column=0, columnspan=2, pady=(8, 0))

load_zones()
update_zone_label()

if pynput_mouse is not None:
    _listener = pynput_mouse.Listener(on_click=_on_global_click)
    _listener.daemon = True
    _listener.start()

info, err = ensure_connected()
if err:
    set_status(err, error=True)
else:
    ready = f"Ready — {SYMBOL}, lot {LOT}, SL {SL_POINTS} / TP {TP_POINTS} points"
    if pynput_mouse is None:
        ready += "  (auto mode off: pynput not installed)"
    set_status(ready)

root.mainloop()
