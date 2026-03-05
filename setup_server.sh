#!/bin/bash
set -e

echo "=== [1/5] Swap 메모리 추가 (2GB) ==="
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "Swap 생성 완료"
else
    echo "Swap 이미 존재"
fi
free -h

echo "=== [2/5] Git clone ==="
if [ ! -d ~/baletAuto ]; then
    git clone https://github.com/limjhily/baletAuto.git ~/baletAuto
else
    cd ~/baletAuto && git pull
fi

echo "=== [3/5] Python 가상환경 + 패키지 설치 ==="
cd ~/baletAuto
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install playwright requests python-dateutil

echo "=== [4/5] Playwright 브라우저 설치 ==="
playwright install chromium
playwright install-deps chromium

echo "=== [5/5] 타임존 설정 (한국) ==="
sudo timedatectl set-timezone Asia/Seoul

echo ""
echo "========================================="
echo "✅ 서버 셋업 완료!"
echo "========================================="
echo "Python: $(python3 --version)"
echo "시간대: $(timedatectl show --property=Timezone --value)"
echo "메모리:"
free -h
