@echo off
cd /d "%~dp0"
echo.
echo   Westerbergen Guest Insights
echo   ===========================
echo.
echo   De app opent automatisch in je browser.
echo   Sluit dit venster om de app te stoppen.
echo.
python -m streamlit run app/main.py --server.port 8501 --server.headless false
pause
