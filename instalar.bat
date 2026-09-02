@echo off
rem  Roda uma vez, na primeira instalacao (ou quando trocar de maquina).
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Instale o Python primeiro: https://python.org
  echo  Marque "Add Python to PATH" durante a instalacao.
  echo.
  pause
  exit /b 1
)

echo.
echo  Instalando os componentes necessarios. Pode demorar alguns minutos.
echo.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if errorlevel 1 (
  echo.
  echo  A instalacao falhou. Copie a mensagem acima ao pedir ajuda.
) else (
  echo.
  echo  Pronto. Agora e so usar o "Iniciar.bat".
)
echo.
pause
