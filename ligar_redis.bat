@echo off
echo Iniciando Servidor Redis para o Hierarchy Mapper...
cd backend\redis
start redis-server.exe redis.windows.conf
echo Redis iniciado em uma nova janela! Nao a feche enquanto estiver usando o App.
pause
