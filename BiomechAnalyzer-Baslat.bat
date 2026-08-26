@echo off
rem Biomech Analyzer masaustu uygulamasini baslatir.
rem Once paketlenmis surumu dener (dist\), yoksa Python ortamindan calistirir.

set "REPO=%~dp0"

if exist "%REPO%dist\BiomechAnalyzer\BiomechAnalyzer.exe" (
    start "" "%REPO%dist\BiomechAnalyzer\BiomechAnalyzer.exe"
    goto :eof
)

if exist "%REPO%.venv\Scripts\pythonw.exe" (
    set "PYTHONPATH=%REPO%src"
    start "" "%REPO%.venv\Scripts\pythonw.exe" -m biomech_analyzer.main
    goto :eof
)

echo Uygulama bulunamadi.
echo Lutfen once kurulumu yapin (bkz. KULLANIM_KILAVUZU.md):
echo   py -3.10 -m venv .venv
echo   .venv\Scripts\python -m pip install -r requirements.txt
pause
