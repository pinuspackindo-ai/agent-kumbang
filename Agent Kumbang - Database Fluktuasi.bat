@echo off
REM ============================================================
REM  Agent Kumbang - Database Fluktuasi
REM  Tarik Bills + Stock + Pricelist dari HashMicro, lalu upload
REM  ke portal PINUS Tools Purchase. Berjalan di belakang layar.
REM ============================================================
title Agent Kumbang - Database Fluktuasi
cd /d "%~dp0"
".venv\Scripts\python.exe" src\agent_kumbang.py %*
