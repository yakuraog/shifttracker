#!/bin/bash
set -e

echo "=== ShiftTracker Deploy ==="

# 1. Обновление системы
echo "[1/7] Обновление системы..."
apt update -qq && apt upgrade -y -qq

# 2. Установка зависимостей
echo "[2/7] Установка Python, pip, git, nginx..."
apt install -y -qq python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx

# 3. Клонирование репозитория
echo "[3/7] Клонирование проекта..."
cd /opt
if [ -d "shifttracker" ]; then
    cd shifttracker && git pull
else
    git clone https://github.com/yakuraog/shifttracker.git
    cd shifttracker
fi

# 4. Виртуальное окружение и зависимости
echo "[4/7] Создание venv и установка зависимостей..."
python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt

# 5. Создание .env если нет
if [ ! -f .env ]; then
    echo "[5/7] Создание .env..."
    cat > .env << 'ENVEOF'
BOT_TOKEN=ВСТАВЬТЕ_ТОКЕН_БОТА
DATABASE_URL=sqlite+aiosqlite:///shifttracker.db
TIMEZONE=Europe/Moscow
QUEUE_MAX_SIZE=500
WORKER_COUNT=8
LOG_LEVEL=INFO
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
OPERATOR_CHAT_ID=0
ENVEOF
    echo "!!! Отредактируйте /opt/shifttracker/.env — укажите BOT_TOKEN !!!"
else
    echo "[5/7] .env уже существует, пропускаю..."
fi

# 6. Systemd сервис
echo "[6/7] Настройка systemd..."
cat > /etc/systemd/system/shifttracker.service << 'SVCEOF'
[Unit]
Description=ShiftTracker Bot + Admin
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/shifttracker
Environment=PATH=/opt/shifttracker/venv/bin
ExecStart=/opt/shifttracker/venv/bin/uvicorn shifttracker.app:create_app --factory --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable shifttracker

# 7. Nginx reverse proxy
echo "[7/7] Настройка nginx..."
cat > /etc/nginx/sites-available/shifttracker << 'NGXEOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGXEOF

ln -sf /etc/nginx/sites-available/shifttracker /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo ""
echo "=== Деплой завершён! ==="
echo ""
echo "Осталось:"
echo "1. Отредактируйте /opt/shifttracker/.env — укажите BOT_TOKEN"
echo "2. Запустите: systemctl start shifttracker"
echo "3. Проверьте: http://94.103.92.207/admin/login"
echo ""
echo "Управление:"
echo "  systemctl start shifttracker    — запустить"
echo "  systemctl stop shifttracker     — остановить"
echo "  systemctl restart shifttracker  — перезапустить"
echo "  journalctl -u shifttracker -f   — логи в реальном времени"
