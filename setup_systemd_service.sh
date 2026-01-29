#!/bin/bash

# Скрипт для установки systemd сервиса SEO Tools
set -e

echo "🔧 Устанавливаю systemd сервис SEO Tools..."

# Копируем service файл в systemd директорию
echo "📁 Копирую service файл..."
sudo cp seotools.service /etc/systemd/system/

# Перезагружаем systemd
echo "🔄 Перезагружаю systemd daemon..."
sudo systemctl daemon-reload

# Включаем автозапуск сервиса
echo "⚡ Включаю автозапуск сервиса..."
sudo systemctl enable seotools.service

# Запускаем сервис
echo "🚀 Запускаю сервис..."
sudo systemctl start seotools.service

# Проверяем статус
echo "📊 Статус сервиса:"
sudo systemctl status seotools.service --no-pager -l

echo "✅ Сервис установлен и запущен!"
echo ""
echo "📝 Полезные команды:"
echo "   sudo systemctl status seotools           # Статус сервиса"
echo "   sudo systemctl restart seotools          # Перезапуск сервиса"
echo "   sudo systemctl stop seotools             # Остановка сервиса"
echo "   sudo journalctl -u seotools -f           # Логи в реальном времени"
echo "   sudo journalctl -u seotools --since today  # Логи за сегодня"
echo ""
