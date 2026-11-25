@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Run MarvelRivals-Forge from this folder without installing it.
rem No parenthesised blocks: inside one, %ERRORLEVEL% is expanded before the program runs and every
rem failure would exit 0.
set "MRFORGE_ROOT=%~dp0"
if not exist "%MRFORGE_ROOT%.venv\Scripts\python.exe" goto :nopython
"%MRFORGE_ROOT%.venv\Scripts\python.exe" -m mrforge %*
exit /b %ERRORLEVEL%
:nopython
set "PYTHONPATH=%MRFORGE_ROOT%src;%PYTHONPATH%"
python -m mrforge %*
exit /b %ERRORLEVEL%
