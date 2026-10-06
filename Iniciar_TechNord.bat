@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "APP_MAIN=%~dp0main.py"
set "PYTHONW="

REM Prioridade: .venv -> venv -> pythonw global -> pyw global
if exist "%~dp0.venv\Scripts\pythonw.exe" set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe"
if not defined PYTHONW if exist "%~dp0venv\Scripts\pythonw.exe" set "PYTHONW=%~dp0venv\Scripts\pythonw.exe"
if not defined PYTHONW (
    where pythonw.exe >nul 2>&1
    if not errorlevel 1 set "PYTHONW=pythonw.exe"
)
if not defined PYTHONW (
    where pyw.exe >nul 2>&1
    if not errorlevel 1 set "PYTHONW=pyw.exe"
)

if not exist "%APP_MAIN%" (
    powershell -NoProfile -WindowStyle Hidden -Command ^
      "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('main.py não encontrado na pasta do launcher.','Tech Nord - Erro') | Out-Null"
    exit /b 1
)

if not defined PYTHONW (
    powershell -NoProfile -WindowStyle Hidden -Command ^
      "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('Python não encontrado. Instale o Python ou crie um venv/.venv dentro da pasta do projeto.','Tech Nord - Erro') | Out-Null"
    exit /b 1
)

start "" "%PYTHONW%" "%APP_MAIN%"
exit /b 0
