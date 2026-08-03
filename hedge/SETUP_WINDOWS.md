# One-click hedge — Windows setup

Do this on **one PC on a DEMO account first**. Once it works, repeat on the others.

## Step 1 — Install Python (once per PC)

1. Go to [python.org/downloads](https://www.python.org/downloads/) and download Python 3.11 or 3.12.
2. Run the installer. **CHECK the box "Add python.exe to PATH"** at the bottom — this matters.
3. Click **Install Now** and finish.

## Step 2 — Install the MT5 library (once per PC)

1. Press the Windows key, type `cmd`, open **Command Prompt**.
2. Type this and press Enter:
   ```
   pip install MetaTrader5
   ```
3. Wait for "Successfully installed". If it errors, try:
   ```
   py -m pip install MetaTrader5
   ```

## Step 3 — Set up MetaTrader 5

1. Open the MT5 terminal and log in — use a **DEMO account** for the first test.
2. In MT5: **Tools → Options → Expert Advisors** → tick **"Allow automated trading"** → OK.
3. On the top toolbar, make sure the **Algo Trading** button is green/on.
4. Find your gold symbol: in Market Watch (left panel), right-click → **Symbols**, and confirm
   the exact gold name — `XAUUSDb`, `XAUUSD`, `GOLD`? **Note it exactly**, including capitals.

## Step 4 — Put the files on the PC

1. Copy `hedge_button.py` and `run_hedge.bat` into one folder, e.g. `C:\Hedge\`.
2. Right-click `hedge_button.py` → **Open with → Notepad**.
3. Edit the CONFIG lines near the top to match your account:
   ```python
   SYMBOL    = "XAUUSDb"   # <- the EXACT name from Step 3.4
   LOT       = 0.30
   SL_POINTS = 550
   TP_POINTS = 670
   ```
4. Save (Ctrl+S) and close Notepad.

## Step 5 — Launch it

1. Double-click `run_hedge.bat`.
2. A small **Hedge** window appears with a green **SIGNAL BUY** and red **SIGNAL SELL**
   button and says *Ready*. It stays on top of other windows.

If a black window flashes an error instead, read it — it usually means Python isn't on
PATH (redo Step 1) or the library is missing (redo Step 2).

## Step 6 — Test on DEMO (before any real trade)

1. Click **SIGNAL BUY** once.
2. Look at MT5 → **Trade** tab. You should see a **SELL 0.30** gold position appear,
   with a Stop Loss and Take Profit already set.
3. Check the status line in the Hedge window shows the price, SL, and TP — glance that
   they look sensible for gold.
4. Click **CLOSE HEDGE** to flatten the test.
5. Do the same with **SIGNAL SELL** (should open a **BUY 0.30**). Close it.

If both tests open the opposite side with SL/TP attached, it's working. ✅

## Step 7 — Go live

1. Log MT5 into the real CXM account. **Restart the tool** after switching accounts.
2. Start with one small trade to confirm, then hand it to the operator.

## Step 8 — Link to Tradovate (one click fires both)

With this on, your **normal single click** on Tradovate's Buy/Sell button also fires
the MT5 hedge — no second cursor, no macro.

1. Install one extra library (once per PC). In Command Prompt:
   ```
   py -m pip install pynput
   ```
   Then close and relaunch the Hedge tool.
2. Open Tradovate and arrange your screen how you'll actually trade
   (Tradovate visible, Hedge window floating on top). **Don't move or resize
   the Tradovate window after this** — the link remembers screen positions.
3. In the Hedge window click **SET BUY ZONE**, then move the mouse onto
   Tradovate's **BUY button** and hold it there. A 5-second countdown runs in
   the status line; when it hits zero the spot is saved. (Hover only — do not click.)
4. Do the same with **SET SELL ZONE** over Tradovate's SELL button.
5. Click **AUTO-HEDGE: OFF** so it turns orange and says **AUTO-HEDGE: ON**.
6. **Test on DEMO/sim on both platforms:** click Tradovate's Buy button once.
   Tradovate takes your trade as normal, and the Hedge status line should show
   `AUTO: SELL 0.30 ...` with the MT5 position appearing in the Trade tab.
   Test the Sell side too, then CLOSE HEDGE and flatten Tradovate.

Rules to remember:

- **Turn AUTO-HEDGE OFF when you're done trading** — while it's ON, any click
  within ~45 px of the saved spots fires a hedge, whatever window is on top.
- If you move/resize the Tradovate window or change monitor setup, **re-set both
  zones** — otherwise clicks miss the zones (no hedge) or fire from the wrong place.
- Repeat clicks within 3 seconds are ignored on purpose (double-click protection).
- The zones are saved to `hedge_zones.json` in the same folder, so they survive
  a relaunch — but still glance at the test after every fresh start of the day.

## Level 2 bot (0.54 lot)

`hedge_button_L2.py` + `run_hedge_L2.bat` are an identical copy of Level 1 with
lot **0.54** (same SL 550 / TP 670 points). Everything above applies the same way:

- Put both files in the same folder, edit the `SYMBOL` line in
  `hedge_button_L2.py` too, and launch with `run_hedge_L2.bat`.
- It has its **own** SET BUY/SELL ZONE and AUTO toggle, saved separately
  (`hedge_zones_L2.json`), so set its zones once as well.
- Each level's **CLOSE HEDGE only closes its own trades** — L1 and L2 tag their
  positions differently and never touch each other's.
- **Careful running both at once:** if L1 and L2 are BOTH open with AUTO ON and
  zones on the same Tradovate buttons, one click fires BOTH hedges
  (0.30 + 0.54 = 0.84 lots). Keep AUTO on in only one level at a time unless
  that is exactly what you want.

## Notes

- **CLOSE HEDGE only closes trades this tool opened** (it tags them internally),
  so it won't touch positions opened manually or by anything else.
- The MT5 terminal must be **running and logged in** while the tool is used.
- If you change the symbol/lot/SL/TP in `hedge_button.py`, close and relaunch the tool.
