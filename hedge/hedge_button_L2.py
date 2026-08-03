"""
One-click hedge tool for MetaTrader 5, with Tradovate click-link.

Symbol box (top of window):
  Type your broker's exact gold symbol (XAUUSD, XAUUSDb, GOLD...) and
  press SET. It is checked live against MT5 and remembered between runs.

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

Requires: Python 3.11+, `pip install MetaTrader5 pynput`, and a running,
logged-in MT5 terminal with "Allow automated trading" enabled.
"""

import json
import os
import time
import tkinter as tk
from tkinter import messagebox

# ===================== CONFIG =====================
LEVEL     = "L2"        # bot name shown in the window
LOT       = 0.54        # trade size in lots
SL_POINTS = 550         # stop-loss distance, in points
TP_POINTS = 670         # take-profit distance, in points
# Symbol is set inside the app (symbol box, top of the window).
DEFAULT_SYMBOL = "XAUUSDb"
# ==================================================

MAGIC       = 909254        # tag so CLOSE HEDGE only touches our own trades
COMMENT     = "hedge-button-L2"
DEVIATION   = 30            # max slippage in points
ZONE_RADIUS = 45            # pixels around the saved spot that count as "on the button"
COOLDOWN_S  = 3             # ignore repeat clicks in the same zone for this many seconds

SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), f"hedge_settings_{LEVEL}.json"
)

# ------------------- theme (futuristic dark) -------------------
BG     = "#0b0f14"   # window background
PANEL  = "#121a26"   # inputs / secondary buttons
FG     = "#dbe7ff"   # main text
DIM    = "#5c7089"   # secondary text
ACCENT = "#00e5ff"   # cyan accent
BUY_C  = "#00c853"   # buy green
SELL_C = "#ff2d55"   # sell red
WARN   = "#ff9100"   # auto-on orange
OK_C   = "#00e676"   # status ok
ERR_C  = "#ff5252"   # status error
DARKTX = "#03110a"   # dark text on bright buttons
FONT   = "Bahnschrift"

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


# ------------------------- settings -------------------------

settings = {"symbol": DEFAULT_SYMBOL, "buy": None, "sell": None}
SYMBOL = DEFAULT_SYMBOL


def load_settings():
    global SYMBOL
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data.get("symbol"), str) and data["symbol"].strip():
            settings["symbol"] = data["symbol"].strip()
        for k in ("buy", "sell"):
            if isinstance(data.get(k), list) and len(data[k]) == 2:
                settings[k] = [int(data[k][0]), int(data[k][1])]
    except (OSError, ValueError):
        pass
    SYMBOL = settings["symbol"]


def save_settings():
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f)
    except OSError:
        pass


# ---------------------------- MT5 ----------------------------

def ensure_connected():
    """Connect to the running MT5 terminal and make the symbol visible."""
    if mt5.terminal_info() is None:
        if not mt5.initialize():
            return None, f"Cannot connect to MT5 (error {mt5.last_error()}). Is the terminal running and logged in?"
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return None, f'Symbol "{SYMBOL}" not found. Type the exact Market Watch name in the box and press SET.'
    if not info.visible:
        if not mt5.symbol_select(SYMBOL, True):
            return None, f'Could not add "{SYMBOL}" to Market Watch.'
        info = mt5.symbol_info(SYMBOL)
    return info, None


def apply_symbol():
    """Validate the typed symbol against MT5, then save and use it."""
    global SYMBOL
    name = symbol_entry.get().strip()
    if not name:
        set_status("Type a symbol first (e.g. XAUUSD or XAUUSDb).", error=True)
        return
    if mt5.terminal_info() is None and not mt5.initialize():
        SYMBOL = name
        settings["symbol"] = name
        save_settings()
        set_status(f'Saved "{name}" — could not verify it (MT5 not running). Start MT5 and press SET again.', error=True)
        return
    if mt5.symbol_info(name) is None:
        set_status(f'"{name}" not found on this account. Check Market Watch → right-click → Symbols.', error=True)
        return
    mt5.symbol_select(name, True)
    SYMBOL = name
    settings["symbol"] = name
    save_settings()
    set_status(f"Symbol set: {name} ✓  (lot {LOT}, SL {SL_POINTS} / TP {TP_POINTS} pts)")


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
        # Re-anchor SL/TP to the actual fill price so the distances are
        # exactly SL_POINTS / TP_POINTS even if the fill slipped.
        fill = result.price
        if abs(fill - price) >= point / 2:
            if order_type == mt5.ORDER_TYPE_SELL:
                sl = fill + SL_POINTS * point
                tp = fill - TP_POINTS * point
            else:
                sl = fill - SL_POINTS * point
                tp = fill + TP_POINTS * point
            mt5.order_send({
                "action":   mt5.TRADE_ACTION_SLTP,
                "symbol":   SYMBOL,
                "position": result.order,
                "sl":       round(sl, digits),
                "tp":       round(tp, digits),
            })
        set_status(
            f"{prefix}{side} {LOT} {SYMBOL} @ {fill:.{digits}f}  "
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

auto_on = False
_last_fire = 0.0
_capturing = False


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
        settings[kind] = [int(x), int(y)]
        save_settings()
        _capturing = False
        update_zone_label()
        set_status(f"{kind.upper()} zone saved at ({int(x)}, {int(y)}). Don't move/resize the Tradovate window now.")


def toggle_auto():
    global auto_on
    if pynput_mouse is None:
        set_status("Auto mode needs pynput. Run:  py -m pip install pynput  then relaunch.", error=True)
        return
    if not auto_on and settings["buy"] is None and settings["sell"] is None:
        set_status("Set the BUY/SELL zones first (SET BUY ZONE, then hover over Tradovate's button).", error=True)
        return
    auto_on = not auto_on
    if auto_on:
        auto_btn.config(text="AUTO-HEDGE  ●  ON", bg=WARN, fg=DARKTX, activebackground="#c56f00")
        set_status("AUTO ON — your click on the Tradovate button will also fire the hedge.")
    else:
        auto_btn.config(text="AUTO-HEDGE  ○  OFF", bg=PANEL, fg=DIM, activebackground="#1a2536")
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
    if _in_zone(x, y, settings["buy"]):
        _last_fire = now
        root.after(0, lambda: open_hedge(True, source="auto"))
    elif _in_zone(x, y, settings["sell"]):
        _last_fire = now
        root.after(0, lambda: open_hedge(False, source="auto"))


# ---------------------------- UI ----------------------------

def set_status(text, error=False):
    status.config(text=text, fg=(ERR_C if error else OK_C))
    root.update_idletasks()


def update_zone_label():
    buy_s = "SET" if settings["buy"] else "—"
    sell_s = "SET" if settings["sell"] else "—"
    zone_label.config(text=f"ZONES   BUY [{buy_s}]   SELL [{sell_s}]")


def flat_btn(parent, text, command, bg, fg, active, font_size=11, width=14, height=1):
    return tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=active, activeforeground=fg,
        font=(FONT, font_size, "bold"), width=width, height=height,
        relief="flat", bd=0, cursor="hand2",
        highlightthickness=0,
    )


load_settings()

root.deiconify()
root.title(f"HEDGE {LEVEL}")
root.configure(bg=BG)
root.attributes("-topmost", True)
root.resizable(False, False)

frame = tk.Frame(root, bg=BG, padx=16, pady=14)
frame.pack()

# header
tk.Label(
    frame, text=f"◈ HEDGE {LEVEL}", font=(FONT, 13, "bold"),
    bg=BG, fg=ACCENT, anchor="w",
).grid(row=0, column=0, sticky="w")
tk.Label(
    frame, text=f"{LOT} LOT · SL {SL_POINTS} · TP {TP_POINTS}", font=(FONT, 9),
    bg=BG, fg=DIM, anchor="e",
).grid(row=0, column=1, sticky="e")

# symbol row
sym_row = tk.Frame(frame, bg=BG)
sym_row.grid(row=1, column=0, columnspan=2, sticky="we", pady=(10, 2))
tk.Label(sym_row, text="SYMBOL", font=(FONT, 9, "bold"), bg=BG, fg=DIM).pack(side="left")
symbol_entry = tk.Entry(
    sym_row, font=(FONT, 12, "bold"), width=14,
    bg=PANEL, fg=FG, insertbackground=ACCENT,
    relief="flat", bd=0, highlightthickness=1,
    highlightbackground="#1e2a3d", highlightcolor=ACCENT,
    justify="center",
)
symbol_entry.pack(side="left", padx=8, ipady=5)
symbol_entry.insert(0, SYMBOL)
symbol_entry.bind("<Return>", lambda e: apply_symbol())
flat_btn(sym_row, "SET", apply_symbol, ACCENT, DARKTX, "#00b3c9", font_size=10, width=6).pack(side="left", ipady=3)

# signal buttons
flat_btn(frame, "SIGNAL BUY", lambda: open_hedge(True), BUY_C, DARKTX, "#00993f",
         font_size=15, width=13, height=2).grid(row=2, column=0, padx=(0, 5), pady=(10, 4), sticky="we")
flat_btn(frame, "SIGNAL SELL", lambda: open_hedge(False), SELL_C, "#1a0308", "#c91736",
         font_size=15, width=13, height=2).grid(row=2, column=1, padx=(5, 0), pady=(10, 4), sticky="we")

# close
flat_btn(frame, "CLOSE HEDGE — FLAT", close_hedges, PANEL, FG, "#1a2536",
         font_size=11, width=30).grid(row=3, column=0, columnspan=2, pady=(4, 2), sticky="we", ipady=4)

# zone buttons
flat_btn(frame, "SET BUY ZONE", lambda: capture_zone("buy"), PANEL, BUY_C, "#1a2536",
         font_size=9, width=14).grid(row=4, column=0, padx=(0, 5), pady=(10, 2), sticky="we", ipady=3)
flat_btn(frame, "SET SELL ZONE", lambda: capture_zone("sell"), PANEL, SELL_C, "#1a2536",
         font_size=9, width=14).grid(row=4, column=1, padx=(5, 0), pady=(10, 2), sticky="we", ipady=3)

# auto toggle
auto_btn = flat_btn(frame, "AUTO-HEDGE  ○  OFF", toggle_auto, PANEL, DIM, "#1a2536",
                    font_size=11, width=30)
auto_btn.grid(row=5, column=0, columnspan=2, pady=2, sticky="we", ipady=5)

zone_label = tk.Label(frame, text="", font=(FONT, 8), bg=BG, fg=DIM)
zone_label.grid(row=6, column=0, columnspan=2, pady=(4, 0))

status = tk.Label(
    frame, text="Ready", font=(FONT, 10), bg=BG, fg=OK_C,
    wraplength=360, justify="left",
)
status.grid(row=7, column=0, columnspan=2, pady=(8, 0), sticky="w")

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
