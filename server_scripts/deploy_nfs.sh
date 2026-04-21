#!/bin/bash

set -e

log_info() {
    echo -e "[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warn() {
    echo -e "[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_ok() {
    echo -e "[OK]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Этот скрипт должен быть запущен с правами root"
        exit 1
    fi
}

install_utilities() {
    log_info "ЭТАП 1: Установка или обновление необходимых утилит"

    log_info "Обновление списка пакетов..."
    apt update || {
        log_error "Не удалось обновить список пакетов"
        exit 1
    }

    PACKAGES="nfs-kernel-server nfs-common tar rsync cron"

    log_info "Установка/обновление пакетов: $PACKAGES"
    apt install -y $PACKAGES || {
        log_error "Не удалось установить необходимые пакеты"
        exit 1
    }
    
    log_ok "Все необходимые утилиты установлены"
}

setup_filesystem() {
    log_info "ЭТАП 2: Настройка файловой системы"

    log_info "Создание директорий для данных студентов..."
    mkdir -p /data/students
    log_ok "Директории для данных созданы"

    log_info "Создание точки монтирования NFS..."
    mkdir -p /srv/nfs4/students
    log_ok "Точка монтирования NFS создана"

    log_info "Монтирование /data/students в /srv/nfs4/students..."
    mount --bind /data/students /srv/nfs4/students || {
        log_error "Не удалось смонтировать директорию"
        exit 1
    }
    log_ok "Директория успешно смонтирована"

    log_info "Добавление записи в /etc/fstab для автомонтирования..."
    FSTAB_ENTRY="/data/students  /srv/nfs4/students  none  bind  0  0"

    if ! grep -qF "$FSTAB_ENTRY" /etc/fstab; then
        echo "$FSTAB_ENTRY" >> /etc/fstab
        log_ok "Запись добавлена в /etc/fstab"
    else
        log_warn "Запись уже существует в /etc/fstab"
    fi
}

configure_nfs() {
    log_info "ЭТАП 3: Настройка NFS сервиса"

    if [ -f /etc/nfs.conf ]; then
        log_info "Создание резервной копии /etc/nfs.conf..."
        cp /etc/nfs.conf /etc/nfs.conf.backup.$(date +%Y%m%d_%H%M%S)
    fi

    log_info "Настройка /etc/nfs.conf..."
    cat > /etc/nfs.conf << 'EOF'
[lockd]
port=32767

[mountd]
manage-gids=y
port=20048

[nfsd]
threads=8
port=2049
vers2=n
vers3=y
vers4=y
vers4.0=y
vers4.1=y
vers4.2=y

[statd]
port=32765
outgoing-port=32766
EOF
    log_ok "Файл /etc/nfs.conf настроен"

    if [ -f /etc/exports ]; then
        log_info "Создание резервной копии /etc/exports..."
        cp /etc/exports /etc/exports.backup.$(date +%Y%m%d_%H%M%S)
    fi

    log_info "Настройка /etc/exports..."
    EXPORT_LINE="/srv/nfs4/students *(rw,sync,no_subtree_check,fsid=0,crossmnt,insecure,root_squash,sec=sys)"

    if ! grep -qF "/srv/nfs4/students" /etc/exports; then
        echo "$EXPORT_LINE" >> /etc/exports
        log_ok "Экспорт добавлен в /etc/exports"
    else
        log_warn "Экспорт уже существует в /etc/exports"
    fi

    log_info "Применение конфигурации экспортов..."
    exportfs -arv || {
        log_error "Не удалось применить конфигурацию экспортов"
        exit 1
    }
    log_ok "Конфигурация экспортов применена"

    log_info "Перезапуск NFS сервиса..."
    systemctl restart nfs-kernel-server || {
        log_error "Не удалось перезапустить NFS сервис"
        exit 1
    }
    log_ok "NFS сервис перезапущен"

    log_info "Включение автозапуска NFS сервиса..."
    systemctl enable nfs-kernel-server || {
        log_error "Не удалось включить автозапуск NFS"
        exit 1
    }
    log_ok "Автозапуск NFS включен"

    log_info "Проверка статуса NFS сервиса..."
    if systemctl is-active --quiet nfs-kernel-server; then
        log_ok "NFS сервис работает корректно"
    else
        log_error "NFS сервис не запущен"
        exit 1
    fi
}

setup_backup() {
    log_info "ЭТАП 4: Настройка программы бэкапов"

    BACKUP_SCRIPTS_DIR="/opt/backup"

    if [ ! -f "$BACKUP_SCRIPTS_DIR/backup.sh" ]; then
        log_error "Скрипт backup.sh не найден в $BACKUP_SCRIPTS_DIR"
        exit 1
    fi

    if [ ! -f "$BACKUP_SCRIPTS_DIR/restore.sh" ]; then
        log_error "Скрипт restore.sh не найден в $BACKUP_SCRIPTS_DIR"
        exit 1
    fi

    if [ ! -f "$BACKUP_SCRIPTS_DIR/transport.sh" ]; then
        log_error "Скрипт transport.sh не найден в $BACKUP_SCRIPTS_DIR"
        exit 1
    fi

    if [ ! -f "$BACKUP_SCRIPTS_DIR/backup.conf" ]; then
        log_error "Файл backup.conf не найден в $BACKUP_SCRIPTS_DIR"
        exit 1
    fi

    log_ok "Все скрипты бэкапов найдены"

    log_info "Установка прав на выполнение скриптов бэкапов..."
    chmod +x "$BACKUP_SCRIPTS_DIR/backup.sh"
    chmod +x "$BACKUP_SCRIPTS_DIR/restore.sh"
    chmod +x "$BACKUP_SCRIPTS_DIR/transport.sh"
    log_ok "Права на выполнение установлены"

    log_info "Создание директорий для хранения бэкапов..."
    mkdir -p /backup/onsite
    mkdir -p /backup/offsite
    mkdir -p /opt/backup/logs
    log_ok "Директории для бэкапов созданы"

    log_info "Настройка расписания резервного копирования через cron..."

    CRON_JOB="0 2 * * * $BACKUP_SCRIPTS_DIR/backup.sh >> /opt/backup/logs/cron.log 2>&1"

    if ! crontab -l 2>/dev/null | grep -qF "$BACKUP_SCRIPTS_DIR/backup.sh"; then
        (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
        log_ok "Задача cron добавлена (ежедневно в 2:00)"
    else
        log_warn "Задача cron уже существует"
    fi

    log_info "Проверка статуса cron сервиса..."
    systemctl enable cron
    systemctl start cron
    
    if systemctl is-active --quiet cron; then
        log_ok "Cron сервис работает"
    else
        log_error "Cron сервис не запущен"
        exit 1
    fi
}

verify_deployment() {
    log_info "Проверка развертывания системы..."

    if mountpoint -q /srv/nfs4/students; then
        log_ok "Директория /srv/nfs4/students смонтирована"
    else
        log_error "Директория /srv/nfs4/students не смонтирована"
        return 1
    fi

    if exportfs | grep -q "/srv/nfs4/students"; then
        log_ok "NFS экспорт активен"
    else
        log_error "NFS экспорт не найден"
        return 1
    fi

    if systemctl is-active --quiet nfs-kernel-server; then
        log_ok "NFS сервис активен"
    else
        log_error "NFS сервис не активен"
        return 1
    fi

    log_ok "Проверка развертывания завершена успешно"
}

main() {
    log_info "==================================================================="
    log_info "Начало развертывания системы сетевого файлового хранилища NFS"
    log_info "==================================================================="

    check_root

    install_utilities
    echo ""

    setup_filesystem
    echo ""

    configure_nfs
    echo ""

    setup_backup
    echo ""

    verify_deployment
    echo ""

    log_ok "==================================================================="
    log_ok "Развертывание системы успешно завершено!"
    log_ok "==================================================================="

    echo ""
    log_info "Информация о развернутой системе:"
    log_info "  - Директория данных: /data/students"
    log_info "  - Точка монтирования NFS: /srv/nfs4/students"
    log_info "  - Локальные бэкапы: /backup/onsite"
    log_info "  - Удаленные бэкапы: /backup/offsite"
    log_info "  - Логи бэкапов: /opt/backup/logs"
    log_info "  - Расписание бэкапов: ежедневно в 2:00"
    echo ""
    log_info "Для просмотра экспортов NFS выполните: exportfs -v"
    log_info "Для просмотра статуса NFS выполните: systemctl status nfs-kernel-server"
    log_info "Для ручного запуска бэкапа выполните: /opt/backup/backup.sh"
}

main "$@"
