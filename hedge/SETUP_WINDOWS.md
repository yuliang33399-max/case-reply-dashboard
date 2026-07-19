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

## Notes

- **CLOSE HEDGE only closes trades this tool opened** (it tags them internally),
  so it won't touch positions opened manually or by anything else.
- The MT5 terminal must be **running and logged in** while the tool is used.
- If you change the symbol/lot/SL/TP in `hedge_button.py`, close and relaunch the tool.
