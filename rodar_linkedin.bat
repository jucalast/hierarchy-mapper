@echo off
title LINKB2B - HierarchyScan Terminal
chcp 65001 > nul
cls
echo =====================================================================
echo               LINKB2B - HIERARCHYSCAN TERMINAL (LinkedIn)
echo =====================================================================
echo.
echo Esse terminal exibira em tempo real todo o processo de automacao,
echo rolagens de pagina e contagem de perfis extraidos do LinkedIn.
echo.
echo ---------------------------------------------------------------------
set /p url="Digite a URL da empresa (ou Pressione ENTER para Grupo Brasa): "
if "%url%"=="" set url="https://www.linkedin.com/company/grupobrasa/people/"
echo ---------------------------------------------------------------------
echo.
echo [INFO] Alvo: %url%
echo [INFO] Iniciando navegador Chromium isolado...
echo [INFO] Aguarde a janela do navegador abrir e faca seu login no LinkedIn...
echo.

backend\venv\Scripts\python.exe -X utf8 backend\scripts\test_hierarchy_scan.py %url%

echo.
echo =====================================================================
echo Processo concluido! O arquivo de saida JSON foi salvo em backend\tmp\
echo =====================================================================
echo.
pause
