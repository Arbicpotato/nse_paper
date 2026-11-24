@echo off
cd /d C:\nse_paper
start "" "C:\nse_paper\.venv\Scripts\pythonw.exe" main.py dash
"C:\nse_paper\.venv\Scripts\python.exe" main.py evening >> evening.log 2>&1
