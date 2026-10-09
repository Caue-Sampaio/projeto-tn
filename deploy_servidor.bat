@echo off
REM ================================================================
REM  deploy_servidor.bat — Copia o TechNord empacotado para o servidor
REM  Execute este script NO COMPUTADOR ONDE VOCÊ FEZ O BUILD
REM ================================================================
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo  TechNord — Deploy para Servidor de Rede
echo ============================================================
echo.

REM ---------------------------------------------------------------
REM  CONFIGURE AQUI o caminho da pasta compartilhada do servidor
REM ---------------------------------------------------------------
set "SERVIDOR=\\SERVIDOR\TechNord"

REM Se o argumento for passado na linha de comando, usa ele
if not "%~1"=="" set "SERVIDOR=%~1"

echo  Destino: %SERVIDOR%
echo.

REM Verifica se o build existe
if not exist "dist\TechNord\TechNord.exe" (
    echo [ERRO] Nao encontrou dist\TechNord\TechNord.exe
    echo        Execute build.bat primeiro!
    pause
    exit /b 1
)

REM Verifica acesso ao servidor
if not exist "%SERVIDOR%" (
    echo [INFO] Pasta %SERVIDOR% nao existe. Criando...
    mkdir "%SERVIDOR%" 2>nul
    if errorlevel 1 (
        echo [ERRO] Nao foi possivel criar a pasta no servidor.
        echo        Verifique se o caminho esta correto e se voce tem permissao.
        echo.
        echo  Uso: deploy_servidor.bat \\NOME-DO-SERVIDOR\PastaCompartilhada
        pause
        exit /b 1
    )
)

echo [1/4] Copiando aplicacao para o servidor...
robocopy "dist\TechNord" "%SERVIDOR%" /MIR /NFL /NDL /NJH /NJS /NC /NS /NP
if errorlevel 8 (
    echo [ERRO] Falha ao copiar arquivos. Verifique permissoes.
    pause
    exit /b 1
)

echo [2/4] Criando pasta de dados compartilhados...
set "DADOS=%SERVIDOR%\Dados"
if not exist "%DADOS%" mkdir "%DADOS%"
if not exist "%DADOS%\db" mkdir "%DADOS%\db"
if not exist "%DADOS%\documents" mkdir "%DADOS%\documents"
if not exist "%DADOS%\reports" mkdir "%DADOS%\reports"
if not exist "%DADOS%\board_images" mkdir "%DADOS%\board_images"
if not exist "%DADOS%\logs" mkdir "%DADOS%\logs"
if not exist "%DADOS%\backups" mkdir "%DADOS%\backups"

echo [3/4] Configurando rede (SQLite compartilhado)...
REM Cria network_config.json apontando para o banco na pasta de dados
(
echo {
echo   "mode": "sqlite",
echo   "sqlite_path": "%DADOS:\=\\%\\db\\technord.db",
echo   "postgres": {
echo     "host": "",
echo     "port": 5432,
echo     "database": "technord",
echo     "user": "technord_app",
echo     "password": "",
echo     "connect_timeout": 5
echo   },
echo   "shared_storage": "%DADOS:\=\\%"
echo }
) > "%SERVIDOR%\network_config.json"

echo [4/4] Criando atalho para os clientes...
REM Cria um script VBS que pode ser copiado para os desktops dos clientes
(
echo Option Explicit
echo Dim shell, fso
echo Set shell = CreateObject^("WScript.Shell"^)
echo Set fso = CreateObject^("Scripting.FileSystemObject"^)
echo shell.Run Chr^(34^) ^& "%SERVIDOR%\TechNord.exe" ^& Chr^(34^), 1, False
) > "%SERVIDOR%\Iniciar_TechNord_Rede.vbs"

echo.
echo ============================================================
echo  DEPLOY CONCLUIDO COM SUCESSO!
echo ============================================================
echo.
echo  Aplicacao:  %SERVIDOR%\TechNord.exe
echo  Dados:      %DADOS%
echo  Atalho:     %SERVIDOR%\Iniciar_TechNord_Rede.vbs
echo.
echo  PROXIMOS PASSOS:
echo    1. No servidor, compartilhe a pasta "%SERVIDOR%"
echo       com permissao de LEITURA+EXECUCAO para todos
echo    2. Compartilhe "%DADOS%" com permissao de
echo       LEITURA+ESCRITA para todos
echo    3. Em cada PC cliente, copie o arquivo
echo       "Iniciar_TechNord_Rede.vbs" para a area de trabalho
echo    4. (Opcional) Crie um atalho .lnk usando o script
echo       "criar_atalho_cliente.bat"
echo ============================================================
echo.
pause
