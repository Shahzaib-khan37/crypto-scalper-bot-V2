@echo off
echo Installing dependencies from requirements.txt...
pip install -r requirements.txt
echo Starting application on port 5000...
set BOT_HOST=127.0.0.1
set BOT_PORT=5000
python app.py
pause
