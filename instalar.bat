@echo off
rem  ------------------------------------------------------------------
rem  Roda UMA VEZ, na primeira instalacao (ou ao trocar de maquina).
rem  Depois disso, o dia a dia e so o "Iniciar.bat".
rem  ------------------------------------------------------------------
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1

echo.
echo  ===============================================
echo   Emissor de NFS-e - instalacao
echo  ===============================================
echo.

rem --- 1. o Python existe? -------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
  echo  [X] O Python nao foi encontrado.
  echo.
  echo      Baixe em https://python.org/downloads
  echo.
  echo      IMPORTANTE: na primeira tela do instalador, marque
  echo      "Add python.exe to PATH" antes de clicar em Install.
  echo      Sem isso o Windows nao acha o Python e este aviso
  echo      aparece de novo.
  echo.
  echo      Ja instalou e continua aparecendo? Feche esta janela,
  echo      abra de novo e tente outra vez -- o Windows so enxerga
  echo      o PATH novo em janelas abertas depois da instalacao.
  echo.
  pause
  exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set VERSAO=%%v
echo  [ok] Python %VERSAO% encontrado.

rem --- 2. versao minima ----------------------------------------------
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if errorlevel 1 (
  echo.
  echo  [X] Este Python e antigo demais ^(precisa ser 3.9 ou mais novo^).
  echo      Instale uma versao atual de https://python.org/downloads
  echo.
  pause
  exit /b 1
)

rem --- 3. bibliotecas -------------------------------------------------
echo.
echo  Instalando os componentes. Pode demorar alguns minutos...
echo.
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo  [X] A instalacao dos componentes falhou.
  echo      Copie a mensagem acima ao pedir ajuda.
  echo.
  pause
  exit /b 1
)
echo.
echo  [ok] Componentes instalados.

rem --- 4. arquivo de senhas -------------------------------------------
rem Sem senha o sistema abre, mas nao assina nota. Criar o arquivo
rem agora, ja com os nomes certos, evita a duvida mais comum depois.
if not exist "config\senhas.bat" (
  if exist "config\senhas.bat.exemplo" (
    copy "config\senhas.bat.exemplo" "config\senhas.bat" >nul
    echo  [!] Criei o config\senhas.bat a partir do exemplo.
    echo      ABRA ele no Bloco de Notas e ponha as senhas de verdade.
  )
) else (
  echo  [ok] config\senhas.bat ja existe.
)

rem --- 5. certificados ------------------------------------------------
if not exist "config\certificados\*.pfx" (
  echo  [!] Nenhum certificado em config\certificados\
  echo      Copie os arquivos .pfx para essa pasta. Sem eles o
  echo      sistema abre e confere tudo, mas nao assina nota.
) else (
  echo  [ok] Certificado encontrado.
)

echo.
echo  ===============================================
echo   Pronto. Agora e so o "Iniciar.bat".
echo  ===============================================
echo.
pause
