@echo off
chcp 65001 >nul
echo ========================================
echo   서비스 재시작
echo ========================================
echo.
ssh -i C:\Users\ebook\.ssh\oracle_baletauto.key.key ubuntu@168.107.26.196 "sudo systemctl restart balet-scheduler balet-bot && sudo systemctl status balet-scheduler balet-bot --no-pager -l"
echo.
echo ========================================
echo   재시작 완료!
echo ========================================
pause
