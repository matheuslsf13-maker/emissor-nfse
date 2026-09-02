@echo off
rem  ------------------------------------------------------------------
rem  Publica uma versao nova para as maquinas que ja rodam o sistema.
rem
rem      publicar.bat 1.4.0
rem      publicar.bat 1.4.0 "Corrige o bairro da Cobilandia"
rem
rem  Para um resumo com varios itens, chame o publicar.py direto:
rem      python publicar.py 1.4.0 --github USUARIO/REPO ^
rem             --notas "resumo de uma linha" ^
rem             --novidade "primeira coisa que mudou" ^
rem             --novidade "segunda coisa"
rem
rem  Faz os dois passos de uma vez: monta o pacote (rodando os testes
rem  antes) e prega no "mural" do GitHub, de onde a clinica busca.
rem
rem  Existe porque errar a pasta e o erro mais facil de cometer: rodar
rem  `python publicar.py` de outro lugar da "No such file or directory".
rem  Este arquivo entra na pasta certa sozinho.
rem  ------------------------------------------------------------------
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1

set REPO=matheuslsf13-maker/emissor-nfse

if "%~1"=="" (
  echo.
  echo  Falta o numero da versao.
  echo.
  echo     publicar.bat 1.4.0
  echo     publicar.bat 1.4.0 "o que mudou, em uma frase"
  echo.
  echo  O numero tem que ser MAIOR que o da versao anterior, senao a
  echo  clinica nao reconhece como novidade.
  echo.
  pause
  exit /b 1
)

set VERSAO=%~1
set NOTAS=%~2
if "%NOTAS%"=="" set NOTAS=Melhorias no sistema

echo.
echo  ===============================================
echo   Publicando a versao %VERSAO%
echo  ===============================================
echo.

rem --- o gh esta acessivel? -------------------------------------------
set GH=gh
where gh >nul 2>nul
if errorlevel 1 (
  if exist "%ProgramFiles%\GitHub CLI\gh.exe" (
    set GH="%ProgramFiles%\GitHub CLI\gh.exe"
  ) else (
    echo  [X] O GitHub CLI ^(gh^) nao foi encontrado.
    echo      Instale com:  winget install GitHub.cli
    echo      Depois feche e abra o terminal.
    echo.
    pause
    exit /b 1
  )
)

rem --- 1. montar o pacote, rodando os testes antes ---------------------
python publicar.py %VERSAO% --github %REPO% --notas "%NOTAS%"
if errorlevel 1 (
  echo.
  echo  [X] Nada foi publicado.
  echo      Se algum teste falhou, a mensagem acima diz qual. Corrija
  echo      antes de publicar -- quem esta do outro lado nao sabe
  echo      reverter uma versao quebrada.
  echo.
  pause
  exit /b 1
)

rem --- 2. pregar no mural ---------------------------------------------
echo.
echo  Enviando para o GitHub...
echo.
%GH% release create v%VERSAO% "publicacao\emissor-nfse.zip" "publicacao\manifesto.json" --title "%VERSAO%" --notes "%NOTAS%"
if errorlevel 1 (
  echo.
  echo  [X] Nao consegui criar a release.
  echo.
  echo      Se disse "already exists": esse numero de versao ja foi
  echo      usado. Use o proximo ^(ex.: %VERSAO%.1^) em vez de repetir
  echo      -- refazer uma release com o mesmo nome de arquivo faz o
  echo      GitHub servir o pacote antigo por alguns minutos.
  echo.
  echo      Se pediu login: rode  gh auth login  uma vez.
  echo.
  pause
  exit /b 1
)

echo.
echo  ===============================================
echo   Versao %VERSAO% no ar.
echo.
echo   Na clinica, agora:
echo     Configuracao
echo     Procurar atualizacoes
echo     Instalar
echo   e depois fechar e abrir o programa.
echo  ===============================================
echo.
pause
