@echo off
title LINKB2B - HierarchyScan Terminal
chcp 65001 > nul
cls

backend\venv\Scripts\python.exe backend\scripts\linkedin_log_viewer.py

echo.
echo =====================================================================
echo Terminal de logs encerrado.
echo =====================================================================
pause
