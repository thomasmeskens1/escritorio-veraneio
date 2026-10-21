@echo off
rem Para o trabalhador do plano Max (roda sem janela, então não há janela para fechar).
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object { $_.CommandLine -like '*trabalhador_max.py*' }; $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; if ($p) { 'Trabalhador Max parado.' } else { 'O Trabalhador Max não estava rodando.' }"
timeout /t 3 >nul
