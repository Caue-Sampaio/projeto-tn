@echo off
REM ================================================================
REM  build.bat — Empacota o TechNord com PyInstaller
REM  Executa na raiz do projeto (onde está o main.py)
REM ================================================================
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo  TechNord — Empacotamento com PyInstaller
echo ============================================================
echo.

REM Verifica Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    pause
    exit /b 1
)

REM Verifica PyInstaller
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [INFO] Instalando PyInstaller...
    pip install pyinstaller
)

echo.
echo [1/3] Limpando builds anteriores...
if exist "build" rd /s /q "build"
if exist "dist\TechNord" rd /s /q "dist\TechNord"

echo [2/3] Executando PyInstaller...
python -m PyInstaller technord.spec --noconfirm

if errorlevel 1 (
    echo.
    echo [ERRO] PyInstaller falhou. Verifique os erros acima.
    pause
    exit /b 1
)

echo.
echo [3/3] Verificando resultado...
if exist "dist\TechNord\TechNord.exe" (
    if not exist "dist\TechNord\db" mkdir "dist\TechNord\db"
    if exist "db\teste.db" copy /y "db\teste.db" "dist\TechNord\db\teste.db" >nul
    if exist "imagens" xcopy /e /i /y "imagens" "dist\TechNord\imagens" >nul
    if exist "documents" xcopy /e /i /y "documents" "dist\TechNord\documents" >nul
    if exist "reports" xcopy /e /i /y "reports" "dist\TechNord\reports" >nul
    if exist "config" xcopy /e /i /y "config" "dist\TechNord\config" >nul
    echo.
    echo ============================================================
    echo  SUCESSO! O executavel foi gerado em:
    echo    dist\TechNord\TechNord.exe
    echo.
    echo  Proximos passos:
    echo    1. Copie TODA a pasta dist\TechNord para o servidor
    echo    2. Compartilhe a pasta no servidor
    echo    3. Crie atalhos nos PCs clientes
    echo    (Veja o guia DEPLOY_REDE.md para instrucoes completas)
    echo ============================================================
) else (
    echo [ERRO] TechNord.exe nao foi encontrado em dist\TechNord\
)

echo.
pause
