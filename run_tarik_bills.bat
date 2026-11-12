@echo off
REM Dipakai Windows Task Scheduler untuk menjalankan agent di belakang layar
cd /d "%~dp0"
".venv\Scripts\python.exe" src\tarik_bills.py
