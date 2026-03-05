@echo off
chcp 65001 >nul
echo ========================================
echo   [1/2] GitHub에 코드 업로드
echo ========================================
echo.
cd /d c:\Users\ebook\Desktop\program\baletAuto
git add .
git commit -m "코드 업데이트"
git push origin main
echo.
echo ========================================
echo   [2/2] 서버에 코드 반영 + 재시작
echo ========================================
echo.
ssh -i C:\Users\ebook\.ssh\oracle_baletauto.key.key ubuntu@168.107.26.196 "cd ~/baletAuto && git pull && sudo systemctl restart balet-scheduler balet-bot && echo 업데이트 완료! && sudo systemctl status balet-scheduler balet-bot --no-pager"
echo.
echo ========================================
echo   완료! 
echo ========================================
pause
