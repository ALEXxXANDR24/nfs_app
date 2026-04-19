#!/usr/bin/env bash
# /opt/backup/backup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/backup.conf"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config) CONFIG_FILE="$2"; shift 2 ;;
        *) echo "Неизвестный аргумент: $1"; exit 1 ;;
    esac
done

[[ ! -f "$CONFIG_FILE" ]] && { echo "Конфиг не найден: $CONFIG_FILE"; exit 1; }
source "$CONFIG_FILE"

source "${SCRIPT_DIR}/transport.sh"

mkdir -p "$ONSITE_BACKUP_DIR" "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

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

create_checksum() {
    local archive="$1"
    local archive_dir
    archive_dir="$(dirname "$archive")"
    local archive_name
    archive_name="$(basename "$archive")"

    log_info "Создание контрольной суммы: $archive_name"
    (
        cd "$archive_dir"
        md5sum "$archive_name" > "${archive_name}.md5"
    )

    log_ok "Контрольная сумма создана"
}

verify_checksum() {
    local archive="$1"
    local archive_dir
    archive_dir="$(dirname "$archive")"
    local archive_name
    archive_name="$(basename "$archive")"

    if [[ ! -f "${archive}.md5" ]]; then
        log_error "Файл MD5 не найден: ${archive}.md5"
        return 1
    fi

    log_info "Проверка контрольной суммы: $archive_name"

    if (cd "$archive_dir" && md5sum --check --status "${archive_name}.md5"); then
        log_ok "MD5 верна"
        return 0
    else
        log_error "MD5 НЕ совпадает!"
        return 1
    fi
}

rotate_onsite_backups() {
    log_info "Ротация on-site копий (оставляем $ONSITE_KEEP_COPIES)"

    local archives
    archives=$(find "$ONSITE_BACKUP_DIR" -maxdepth 1 \
        -name "${ARCHIVE_PREFIX}_*.tar.gz" | sort)

    local count
    count=$(echo "$archives" | grep -c . || true)

    if [[ $count -gt $ONSITE_KEEP_COPIES ]]; then
        local to_delete
        to_delete=$(echo "$archives" | head -n $((count - ONSITE_KEEP_COPIES)))
        while IFS= read -r old; do
            log_info "Удаление: $(basename "$old")"
            rm -f "$old" "${old}.md5"
        done <<< "$to_delete"
        log_ok "Ротация on-site завершена"
    else
        log_info "Ротация не требуется (копий: $count)"
    fi
}

rotate_offsite_backups() {
    log_info "Ротация off-site копий (оставляем $OFFSITE_KEEP_COPIES)"

    local archives
    archives=$(transport_list_archives)

    if [[ -z "$archives" ]]; then
        log_info "Off-site архивы не найдены, ротация не требуется"
        return 0
    fi

    local count
    count=$(echo "$archives" | grep -c . || true)

    if [[ $count -gt $OFFSITE_KEEP_COPIES ]]; then
        local to_delete
        to_delete=$(echo "$archives" | head -n $((count - OFFSITE_KEEP_COPIES)))
        while IFS= read -r old; do
            log_info "Удаление off-site: $(basename "$old")"
            transport_remove "$old" "${old}.md5"
        done <<< "$to_delete"
        log_ok "Ротация off-site завершена"
    else
        log_info "Ротация off-site не требуется (копий: $count)"
    fi
}

create_onsite_backup() {
    local required_vars=(
        DATE_FORMAT ARCHIVE_PREFIX ONSITE_BACKUP_DIR SOURCE_DIR LOG_DIR
    )
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_error "Переменная не определена или пустая: $var"
            return 1
        fi
    done

    local timestamp
    timestamp=$(date +"$DATE_FORMAT")
    local archive_name="${ARCHIVE_PREFIX}_${timestamp}.tar.gz"
    local archive_path="${ONSITE_BACKUP_DIR}/${archive_name}"
    local tar_log="${LOG_DIR}/tar_$$.log"

    log_info "=========================================="
    log_info "Создание on-site архива: $archive_name"
    log_info "Источник (содержимое): $SOURCE_DIR"

    if [[ ! -d "$SOURCE_DIR" ]]; then
        log_error "Источник не существует или не является директорией: $SOURCE_DIR"
        return 1
    fi

    if [[ ! -d "$ONSITE_BACKUP_DIR" ]]; then
        log_error "Директория on-site не существует: $ONSITE_BACKUP_DIR"
        return 1
    fi

    local free_space
    free_space=$(df -BG "$ONSITE_BACKUP_DIR" | awk 'NR==2 {gsub("G",""); print $4}')
    if [[ $free_space -lt 1 ]]; then
        log_error "Недостаточно места: ${free_space}G свободно"
        return 1
    fi
    log_info "Свободное место: ${free_space}G"

    if tar \
        --create \
        --gzip \
        --file="$archive_path" \
        --directory="$SOURCE_DIR" \
        --preserve-permissions \
        --verbose \
        . \
        > "$tar_log" 2>&1; then

        while IFS= read -r line; do
            log_info "tar: $line"
        done < "$tar_log"
        rm -f "$tar_log"
        log_ok "Архив создан: $(du -sh "$archive_path" | cut -f1)"
    else
        local exit_code=$?
        while IFS= read -r line; do
            log_error "tar: $line"
        done < "$tar_log"
        rm -f "$tar_log"
        log_error "Ошибка создания архива! Код выхода: $exit_code"
        rm -f "$archive_path"
        return 1
    fi

    create_checksum "$archive_path"

    log_info "Проверка целостности tar..."
    if tar \
        --list \
        --gzip \
        --file="$archive_path" \
        > /dev/null 2>&1; then
        log_ok "Целостность tar подтверждена"
    else
        log_error "Архив повреждён после создания!"
        rm -f "$archive_path" "${archive_path}.md5"
        return 1
    fi

    verify_checksum "$archive_path"

    echo "$archive_path" > "${LOG_DIR}/last_archive.tmp"
}

sync_to_offsite() {
    local archive_path="$1"
    local archive_name
    archive_name=$(basename "$archive_path")

    log_info "=========================================="
    log_info "Синхронизация с off-site"
    log_info "Файл: $archive_name"

    if ! transport_check_host; then
        log_error "Off-site хост недоступен!"
        return 1
    fi

    transport_mkdir "$OFFSITE_DIR"

    if transport_push \
        "$archive_path" \
        "${archive_path}.md5" \
        "$OFFSITE_DIR"; then
        log_ok "Файлы переданы"
    else
        log_error "Ошибка передачи файлов!"
        return 1
    fi

    log_info "Верификация MD5 на off-site..."
    if transport_verify_md5 "${OFFSITE_DIR}/${archive_name}"; then
        log_ok "MD5 на off-site верна"
        return 0
    else
        log_error "MD5 на off-site НЕ совпадает!"
        return 1
    fi
}

main() {
    log_info "=========================================="
    log_info "ЗАПУСК РЕЗЕРВНОГО КОПИРОВАНИЯ"
    log_info "Время: $(date)"
    log_transport_mode
    log_info "=========================================="

    local attempt=0
    local success=false
    local archive_path=""
    local archive_tmp="${LOG_DIR}/last_archive.tmp"

    while [[ $attempt -lt $RETRY_COUNT ]]; do
        attempt=$((attempt + 1))
        log_info "Попытка $attempt из $RETRY_COUNT"

        rm -f "$archive_tmp"
        if create_onsite_backup; then
            archive_path=$(cat "$archive_tmp")
            rm -f "$archive_tmp"
            log_ok "On-site копия создана: $(basename "$archive_path")"
        else
            rm -f "$archive_tmp"
            log_error "Ошибка создания on-site копии (попытка $attempt)"
            [[ $attempt -lt $RETRY_COUNT ]] && sleep "$RETRY_WAIT"
            continue
        fi

        if sync_to_offsite "$archive_path"; then
            log_ok "Off-site синхронизация выполнена"
        else
            log_error "Ошибка off-site синхронизации (попытка $attempt)"
            [[ $attempt -lt $RETRY_COUNT ]] && sleep "$RETRY_WAIT"
            continue
        fi

        rotate_onsite_backups
        rotate_offsite_backups || log_warn "Ошибка ротации off-site"

        success=true
        break
    done

    if $success; then
        log_ok "=========================================="
        log_ok "РЕЗЕРВНОЕ КОПИРОВАНИЕ ЗАВЕРШЕНО УСПЕШНО"
        log_ok "Архив: $(basename "$archive_path")"
        log_ok "Время: $(date)"
        log_ok "=========================================="
        exit 0
    else
        log_error "=========================================="
        log_error "РЕЗЕРВНОЕ КОПИРОВАНИЕ ЗАВЕРШЕНО С ОШИБКОЙ"
        log_error "Исчерпано попыток: $RETRY_COUNT"
        log_error "=========================================="
        send_notification \
            "[BACKUP ERROR] Ошибка резервного копирования" \
            "Хост: $(hostname)\nВремя: $(date)\nЛог: $LOG_FILE"
        exit 1
    fi
}

main "$@"
