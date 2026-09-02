@echo off
rem ---------------------------------------------------------------
rem  Emissor de NFS-e - clique duas vezes neste arquivo para abrir.
rem ---------------------------------------------------------------
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  O Python nao esta instalado nesta maquina.
  echo  Baixe em https://python.org e marque "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

python -c "import flask, pdfplumber, lxml, cryptography" >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Faltam componentes. Rode o "instalar.bat" uma vez antes.
  echo.
  pause
  exit /b 1
)

rem Senhas dos certificados. Crie config\senhas.bat com as linhas:
rem     set CERT_SENHA_GLORIA=suasenha
rem     set CERT_SENHA_COBILANDIA=suasenha
rem Esse arquivo NAO deve ser copiado nem versionado.
if exist "config\senhas.bat" call "config\senhas.bat"

python app.py

if errorlevel 1 (
  echo.
  echo  O programa parou com erro. Copie a mensagem acima ao pedir ajuda.
  pause
)
endlocal
