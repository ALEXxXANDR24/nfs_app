#!/usr/bin/env bash
# /opt/backup/restore.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/backup.conf"
SPECIFIC_ARCHIVE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)  CONFIG_FILE="$2";      shift 2 ;;
        --archive) SPECIFIC_ARCHIVE="$2"; shift 2 ;;
        *) echo "Неизвестный аргумент: $1"; exit 1 ;;
    esac
done

[[ ! -f "$CONFIG_FILE" ]] && { echo "Конфиг не найден: $CONFIG_FILE"; exit 1; }
source "$CONFIG_FILE"

source "${SCRIPT_DIR}/transport.sh"

RESTORE_LOG="${LOG_DIR}/restore_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$RESTORE_LOG") 2>&1

log()       { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$1] $2"; }
log_info()  { log "INFO " "$1"; }
log_warn()  { log "WARN " "$1"; }
log_error() { log "ERROR" "$1"; }
log_ok()    { log "OK   " "$1"; }

send_notification() {
    local subject="$1" message="$2"
    log_info "Отправка уведомления: $subject"
    if command -v mail &>/dev/null; then
        echo "$message" | mail -s "$subject" "$ADMIN_EMAIL"
    else
        log_warn "Почтовый клиент не найден"
    fi
}

check_server_alive() {
    log_info "Проверка доступности сервера..."
    if ping -c 3 -W 5 "$(hostname)" &>/dev/null; then
        log_ok "Сервер доступен"
        return 0
    else
        log_error "Сервер недоступен!"
        return 1
    fi
}

verify_archive_integrity() {
    local archive="$1"
    local archive_dir
    archive_dir="$(dirname "$archive")"
    local archive_name
    archive_name="$(basename "$archive")"

    log_info "Проверка целостности: $archive_name"

    if [[ ! -f "$archive" ]]; then
        log_error "Архив не найден: $archive"
        return 1
    fi

    if [[ ! -f "${archive}.md5" ]]; then
        log_error "Файл MD5 не найден: ${archive}.md5"
        return 1
    fi

    if (cd "$archive_dir" && md5sum --check --status "${archive_name}.md5"); then
        log_ok "MD5 верна"
    else
        log_error "MD5 НЕ совпадает — архив повреждён!"
        return 1
    fi

    if tar \
        --list \
        --gzip \
        --file="$archive" \
        > /dev/null 2>&1; then
        log_ok "Целостность tar подтверждена"
    else
        log_error "Tar архив повреждён!"
        return 1
    fi

    return 0
}

check_onsite_backup() {
    local archive_tmp="$1"

    log_info "Проверка on-site копии..."

    local archive=""
    if [[ -n "$SPECIFIC_ARCHIVE" ]]; then
        archive="${ONSITE_BACKUP_DIR}/${SPECIFIC_ARCHIVE}"
    else
        archive=$(find "$ONSITE_BACKUP_DIR" -maxdepth 1 \
            -name "${ARCHIVE_PREFIX}_*.tar.gz" \
            | sort | tail -n 1)
    fi

    if [[ -z "$archive" ]]; then
        log_warn "On-site архивы не найдены"
        return 1
    fi

    log_info "Найден: $(basename "$archive")"

    if verify_archive_integrity "$archive"; then
        log_ok "On-site копия в порядке"
        echo "$archive" > "$archive_tmp"
        return 0
    else
        log_error "On-site копия повреждена!"
        return 1
    fi
}

check_offsite_backup() {
    local archive_tmp="$1"

    log_info "Проверка off-site копии..."

    if ! transport_check_host; then
        log_error "Off-site хост недоступен!"
        return 1
    fi

    local remote_archive=""
    if [[ -n "$SPECIFIC_ARCHIVE" ]]; then
        remote_archive="${OFFSITE_DIR}/${SPECIFIC_ARCHIVE}"
    else
        remote_archive=$(transport_list_archives | tail -n 1)
    fi

    if [[ -z "$remote_archive" ]]; then
        log_error "Off-site архивы не найдены!"
        return 1
    fi

    log_info "Найден off-site архив: $(basename "$remote_archive")"

    local local_tmp="/tmp/offsite_restore"
    mkdir -p "$local_tmp"
    local archive_name
    archive_name=$(basename "$remote_archive")
    local local_archive="${local_tmp}/${archive_name}"

    log_info "Загрузка off-site архива для верификации..."
    if ! transport_pull \
        "$remote_archive" \
        "${remote_archive}.md5" \
        "$local_tmp"; then
        log_error "Ошибка загрузки off-site архива!"
        rm -rf "$local_tmp"
        return 1
    fi

    if verify_archive_integrity "$local_archive"; then
        log_ok "Off-site копия в порядке"
        echo "$local_archive" > "$archive_tmp"
        return 0
    else
        log_error "Off-site копия повреждена!"
        rm -rf "$local_tmp"
        return 1
    fi
}

is_nfs_running() {
    systemctl is-active --quiet "$NFS_SERVICE" 2>/dev/null
}

stop_nfs() {
    if is_nfs_running; then
        log_info "Остановка NFS ($NFS_SERVICE)..."
        systemctl stop "$NFS_SERVICE"
        log_ok "NFS остановлен"
        return 0
    else
        log_info "NFS уже остановлен"
        return 1
    fi
}

start_nfs() {
    log_info "Запуск NFS ($NFS_SERVICE)..."
    systemctl start "$NFS_SERVICE"
    log_ok "NFS запущен"
}

restore_from_archive() {
    local archive="$1"

    log_info "Восстановление из: $(basename "$archive")"
    log_info "Цель (содержимое): $SOURCE_DIR"

    if [[ ! -d "$SOURCE_DIR" ]]; then
        log_error "Целевая директория не существует: $SOURCE_DIR"
        return 1
    fi

    local tar_log="${LOG_DIR}/tar_restore_$$.log"

    local backup_current="${SOURCE_DIR}_before_restore_$(date +%Y%m%d_%H%M%S)"

    log_info "Сохранение текущего содержимого в: $backup_current"
    mkdir -p "$backup_current"
    if ! rsync \
        --archive \
        --hard-links \
        "${SOURCE_DIR}/" \
        "${backup_current}/"; then
        log_error "Ошибка сохранения текущих данных!"
        rm -rf "$backup_current"
        return 1
    fi
    log_ok "Текущие данные сохранены"

    log_info "Очистка содержимого: $SOURCE_DIR"
    find "$SOURCE_DIR" -mindepth 1 -delete
    log_ok "Содержимое очищено"

    if tar \
        --extract \
        --gzip \
        --file="$archive" \
        --directory="$SOURCE_DIR" \
        --preserve-permissions \
        --verbose \
        > "$tar_log" 2>&1; then

        while IFS= read -r line; do
            log_info "tar: $line"
        done < "$tar_log"
        rm -f "$tar_log"
        log_ok "Данные восстановлены"

        log_info "Удаление временного бэкапа: $(basename "$backup_current")"
        rm -rf "$backup_current"
        log_ok "Временный бэкап удалён"

        return 0
    else
        local exit_code=$?

        while IFS= read -r line; do
            log_error "tar: $line"
        done < "$tar_log"
        rm -f "$tar_log"
        log_error "Ошибка восстановления! Код выхода: $exit_code"

        log_warn "Откат к предыдущему состоянию..."
        find "$SOURCE_DIR" -mindepth 1 -delete
        if rsync \
            --archive \
            --hard-links \
            "${backup_current}/" \
            "${SOURCE_DIR}/"; then
            log_ok "Данные возвращены к предыдущему состоянию"
        else
            log_error "Ошибка отката! Данные могут быть в: $backup_current"
        fi

        return 1
    fi
}

main() {
    log_info "=========================================="
    log_info "ЗАПУСК ВОССТАНОВЛЕНИЯ"
    log_info "Время: $(date)"
    log_info "Хост: $(hostname)"
    log_transport_mode
    log_info "=========================================="

    local nfs_was_running=false
    local restore_archive=""
    local restore_source=""
    local archive_tmp="${LOG_DIR}/last_restore_archive.tmp"

    if ! check_server_alive; then
        send_notification \
            "[RESTORE ALERT] Сервер недоступен" \
            "Хост: $(hostname)\nВремя: $(date)\nЛог: $RESTORE_LOG"
        exit 1
    fi

    log_info "------------------------------------------"
    log_info "ПРОВЕРКА ON-SITE КОПИИ"
    log_info "------------------------------------------"

    rm -f "$archive_tmp"
    if check_onsite_backup "$archive_tmp"; then
        restore_archive=$(cat "$archive_tmp")
        rm -f "$archive_tmp"
        restore_source="onsite"
        log_ok "Используем on-site копию: $(basename "$restore_archive")"
    else
        rm -f "$archive_tmp"

        log_info "------------------------------------------"
        log_info "ПРОВЕРКА OFF-SITE КОПИИ"
        log_info "------------------------------------------"

        if check_offsite_backup "$archive_tmp"; then
            restore_archive=$(cat "$archive_tmp")
            rm -f "$archive_tmp"
            restore_source="offsite"
            log_ok "Используем off-site копию: $(basename "$restore_archive")"
        else
            rm -f "$archive_tmp"
            log_error "ОБЕ КОПИИ ПОВРЕЖДЕНЫ!"
            send_notification \
                "[RESTORE CRITICAL] Все резервные копии повреждены!" \
                "Хост: $(hostname)\nВремя: $(date)\nЛог: $RESTORE_LOG"
            exit 1
        fi
    fi

    log_info "=========================================="
    log_info "ИСТОЧНИК: $restore_source"
    log_info "АРХИВ: $(basename "$restore_archive")"
    log_info "=========================================="

    log_info "------------------------------------------"
    log_info "УПРАВЛЕНИЕ NFS СЕРВИСОМ"
    log_info "------------------------------------------"

    if is_nfs_running; then
        nfs_was_running=true
        stop_nfs
    else
        log_info "NFS сервис не активен, пропуск"
    fi

    log_info "------------------------------------------"
    log_info "ВОССТАНОВЛЕНИЕ ДАННЫХ"
    log_info "------------------------------------------"

    if restore_from_archive "$restore_archive"; then
        log_ok "Восстановление успешно"
    else
        $nfs_was_running && start_nfs
        send_notification \
            "[RESTORE ERROR] Ошибка восстановления" \
            "Хост: $(hostname)\nИсточник: $restore_source\nЛог: $RESTORE_LOG"
        exit 1
    fi

    $nfs_was_running && start_nfs

    if [[ "$restore_source" == "offsite" ]] && ! is_local_offsite; then
        log_info "Очистка временных файлов..."
        rm -rf "/tmp/offsite_restore"
    fi

    log_ok "=========================================="
    log_ok "ВОССТАНОВЛЕНИЕ ЗАВЕРШЕНО УСПЕШНО"
    log_ok "Источник: $restore_source"
    log_ok "Архив: $(basename "$restore_archive")"
    log_ok "Лог: $RESTORE_LOG"
    log_ok "=========================================="

    send_notification \
        "[RESTORE OK] Восстановление завершено успешно" \
        "Хост: $(hostname)\nИсточник: $restore_source\nЛог: $RESTORE_LOG"

    exit 0
}

main "$@"
