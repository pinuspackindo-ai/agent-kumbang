@echo off
REM Tarik semua data HashMicro (Bills + Stock per-Warehouse + Pricelist New) dengan sekali login
cd /d "%~dp0"
".venv\Scripts\python.exe" src\tarik_semua.py
