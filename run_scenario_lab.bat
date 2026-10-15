@echo off
cd /d C:\Users\catji\Projects\invest_provert
call venv\Scripts\activate
python -m scenario_lab.main %*
pause
