@echo off
cd /d C:\Users\catji\Projects\invest_provert
call venv\Scripts\activate
python -m lvmb_momentum.main %*
pause
