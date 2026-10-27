@echo off
set PYTHONPATH=%~dp0transplier-cli;%~dp0;%PYTHONPATH%
C:\Users\Anish\anaconda3\python.exe -m multilang_transpiler.transpiler_cli %*
