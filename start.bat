@echo off
REM Windows: cift tikla -> ilk seferde kurar (tamamlanma bayragiyla), sonra GUI'yi acar.
cd /d "%~dp0"
if not exist venv\.setup_ok (
  echo Ilk kurulum ^(venv + Chromium^) - birkac dakika...
  python -m venv venv || (echo HATA: venv/Python 3 kurulu mu? & pause & exit /b 1)
  call venv\Scripts\pip.exe install --upgrade pip || (echo HATA: pip & pause & exit /b 1)
  call venv\Scripts\pip.exe install -r requirements.txt || (echo HATA: bagimliliklar & pause & exit /b 1)
  call venv\Scripts\python.exe -m playwright install chromium || (echo HATA: Chromium & pause & exit /b 1)
  type nul > venv\.setup_ok
)
venv\Scripts\python.exe click_gui.py
if errorlevel 1 pause
