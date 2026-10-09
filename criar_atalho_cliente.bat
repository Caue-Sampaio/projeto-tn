@echo off
REM ================================================================
REM  criar_atalho_cliente.bat — Cria atalho do TechNord na área de trabalho
REM  Execute este script EM CADA PC CLIENTE da rede
REM ================================================================
setlocal EnableExtensions

REM ---------------------------------------------------------------
REM  CONFIGURE AQUI o caminho de rede do TechNord.exe no servidor
REM ---------------------------------------------------------------
set "TECHNORD_EXE=\\SERVIDOR\TechNord\TechNord.exe"

if not "%~1"=="" set "TECHNORD_EXE=%~1"

echo ============================================================
echo  TechNord — Criador de Atalho para Cliente
echo ============================================================
echo.
echo  Servidor: %TECHNORD_EXE%
echo.

REM Verifica se consegue acessar o servidor
if not exist "%TECHNORD_EXE%" (
    echo [ERRO] Nao foi possivel acessar: %TECHNORD_EXE%
    echo        Verifique se:
    echo          - O servidor esta ligado
    echo          - A pasta esta compartilhada
    echo          - Este PC esta na mesma rede
    echo.
    echo  Uso: criar_atalho_cliente.bat \\NOME-SERVIDOR\TechNord\TechNord.exe
    pause
    exit /b 1
)

REM Cria o atalho na área de trabalho usando PowerShell
set "DESKTOP=%USERPROFILE%\Desktop"
set "ATALHO=%DESKTOP%\TechNord.lnk"

powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell; " ^
    "$s = $ws.CreateShortcut('%ATALHO%'); " ^
    "$s.TargetPath = '%TECHNORD_EXE%'; " ^
    "$s.WorkingDirectory = [System.IO.Path]::GetDirectoryName('%TECHNORD_EXE%'); " ^
    "$s.Description = 'TechNord TestFlow - Sistema de Teste de Placas'; " ^
    "$s.IconLocation = '%TECHNORD_EXE%,0'; " ^
    "$s.Save()"

if exist "%ATALHO%" (
    echo.
    echo [OK] Atalho criado com sucesso!
    echo      %ATALHO%
    echo.
    echo  Basta clicar duas vezes no atalho "TechNord" na
    echo  area de trabalho para iniciar o programa.
) else (
    echo [ERRO] Falha ao criar o atalho.
)

echo.
pause
