@echo off
REM Genera dist\NODORA\NODORA.exe (requiere Python 3.10+ de 64 bits y conexion para instalar paquetes)
setlocal
cd /d "%~dp0"
if not exist .venv ( py -3 -m venv .venv || goto :err )
call .venv\Scripts\activate.bat || goto :err
python -m pip install --upgrade pip || goto :err
pip install -r requirements-dev.txt || goto :err
python tools\make_assets.py || goto :err
pyinstaller --noconfirm --clean --windowed --name NODORA --icon assets\nodora.ico --add-data "assets;assets" main.py || goto :err
echo.
echo Listo: dist\NODORA\NODORA.exe
exit /b 0
:err
echo ERROR: revise los mensajes anteriores.
exit /b 1
