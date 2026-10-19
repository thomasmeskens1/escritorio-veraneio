@echo off
rem Inicia o trabalhador do plano Max minimizado (atalho na pasta Inicializar do Windows).
cd /d "%~dp0"
start "Trabalhador Max - Escritorio Veraneio" /min python "%~dp0trabalhador_max.py"
