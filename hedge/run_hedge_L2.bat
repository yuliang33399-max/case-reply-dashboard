@echo off
title Hedge Launcher L2
cd /d "%~dp0"
where py >nul 2>nul && (py hedge_button_L2.py) || (python hedge_button_L2.py)
if errorlevel 1 (
    echo.
    echo Something went wrong. Is Python installed with "Add to PATH" ticked?
    echo Try opening Command Prompt and running:  pip install MetaTrader5 pynput
    pause
)
