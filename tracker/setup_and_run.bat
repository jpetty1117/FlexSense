@echo off
setlocal
cd /d "%~dp0"
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Dependency installation failed. Make sure Python and internet access are available.
  pause
  exit /b 1
)
python app.py
pause
