@echo off
REM Builds SpiritValeMarket.exe (the "Run it" step, packaged as a single file).
REM Requires: pip install pyinstaller frida flask
cd /d "%~dp0..\.."
python -m PyInstaller --onefile --clean --name SpiritValeMarket --icon "%cd%\extract\frida\app_icon.ico" --add-data "%cd%\extract\frida\combined_hook.js;." --distpath extract\frida --workpath build\pyinstaller --specpath build extract\frida\server.py
echo.
echo Built: extract\frida\SpiritValeMarket.exe
