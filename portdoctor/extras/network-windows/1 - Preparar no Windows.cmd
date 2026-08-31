@echo off
setlocal
title Jogos em Rede R36S
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Preparar Jogos em Rede no Windows.ps1"
if errorlevel 1 (
  echo.
  echo O assistente terminou com erro. Leia a mensagem acima.
  pause
)
endlocal
