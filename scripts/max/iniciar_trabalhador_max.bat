@echo off
rem Inicia o trabalhador do plano Max sem janela (pythonw). Log: backend\dados\trabalhador_max.log
rem Se ele já estiver rodando, a segunda cópia se encerra sozinha.
cd /d "%~dp0"
start "" pythonw "%~dp0trabalhador_max.py"
