@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Run MarvelRivals-Forge from this folder without installing it.
set "MRFORGE_ROOT=%~dp0"
if exist "%MRFORGE_ROOT%.venv\Scripts\python.exe" (
  "%MRFORGE_ROOT%.venv\Scripts\python.exe" -m mrforge %*
  exit /b %ERRORLEVEL%
)
set "PYTHONPATH=%MRFORGE_ROOT%src;%PYTHONPATH%"
python -m mrforge %*
exit /b %ERRORLEVEL%
