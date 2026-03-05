@echo off
chcp 65001 >nul
echo ========================================
echo   서비스 상태 확인
echo ========================================
echo.
ssh -i C:\Users\ebook\.ssh\oracle_baletauto.key.key ubuntu@168.107.26.196 "sudo systemctl status balet-scheduler --no-pager -l && echo. && echo =============================== && echo. && sudo systemctl status balet-bot --no-pager -l"
echo.
echo ========================================
pause
