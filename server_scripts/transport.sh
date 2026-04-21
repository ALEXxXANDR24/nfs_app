#!/usr/bin/env bash
# /opt/backup/transport.sh

is_local_offsite() {
    case "$OFFSITE_HOST" in
        localhost|127.0.0.1|::1)
            return 0
            ;;
        *)
            local machine_hostname
            machine_hostname="$(hostname -f 2>/dev/null || hostname)"
            local machine_short
            machine_short="$(hostname -s 2>/dev/null || hostname)"

            if [[ "$OFFSITE_HOST" == "$machine_hostname" ]] || \
               [[ "$OFFSITE_HOST" == "$machine_short"    ]]; then
                return 0
            fi
            return 1
            ;;
    esac
}

log_transport_mode() {
    if is_local_offsite; then
        log_info "Режим транспорта : LOCAL  (rsync без ssh)"
        log_info "Off-site путь    : ${OFFSITE_DIR}"
    else
        log_info "Режим транспорта : REMOTE (rsync через ssh)"
        log_info "Off-site хост    : ${OFFSITE_USER}@${OFFSITE_HOST}:${OFFSITE_DIR}"
    fi
}

_rsync_base_flags() {
    echo "--archive --compress --progress --stats --human-readable"
}

_rsync_rsh_flag() {
    if is_local_offsite; then
        echo ""
    else
        echo "--rsh=ssh -i ${OFFSITE_SSH_KEY} -o ConnectTimeout=30 -o BatchMode=yes"
    fi
}

_remote_path() {
    local path="$1"
    if is_local_offsite; then
        echo "$path"
    else
        echo "${OFFSITE_USER}@${OFFSITE_HOST}:${path}"
    fi
}

transport_check_host() {
    if is_local_offsite; then
        log_info "Проверка доступности off-site (local)..."

        if [[ -d "$OFFSITE_DIR" ]] || mkdir -p "$OFFSITE_DIR" 2>/dev/null; then
            log_ok "Локальная off-site директория доступна"
            return 0
        else
            log_error "Локальная off-site директория недоступна: $OFFSITE_DIR"
            return 1
        fi
    else
        log_info "Проверка доступности off-site хоста: $OFFSITE_HOST ..."

        if ssh \
            -i "$OFFSITE_SSH_KEY" \
            -o ConnectTimeout=10 \
            -o BatchMode=yes \
            "${OFFSITE_USER}@${OFFSITE_HOST}" \
            "echo ok" &>/dev/null; then

            log_ok "Удалённый хост доступен"
            return 0
        else
            log_error "Удалённый хост недоступен: $OFFSITE_HOST"
            return 1
        fi
    fi
}

transport_exec() {
    local cmd="$1"

    if is_local_offsite; then
        bash -c "$cmd"
    else
        ssh \
            -i "$OFFSITE_SSH_KEY" \
            -o ConnectTimeout=30 \
            -o BatchMode=yes \
            "${OFFSITE_USER}@${OFFSITE_HOST}" \
            "$cmd"
    fi
}

transport_mkdir() {
    local remote_dir="$1"

    log_info "Создание директории на off-site: $remote_dir"
    transport_exec "mkdir -p '${remote_dir}'"
}

transport_push() {
    local args=("$@")
    local dest_dir="${args[-1]}"
    local sources=("${args[@]:0:${#args[@]}-1}")

    log_info "Передача файлов на off-site (dest: $dest_dir)..."
    for src in "${sources[@]}"; do
        log_info "  -> $(basename "$src")"
    done

    local rsync_dest
    rsync_dest="$(_remote_path "$dest_dir")/"

    if is_local_offsite; then
        rsync \
            $(_rsync_base_flags) \
            "${sources[@]}" \
            "$rsync_dest"
    else
        rsync \
            $(_rsync_base_flags) \
            --rsh="ssh -i ${OFFSITE_SSH_KEY} \
                       -o ConnectTimeout=30 \
                       -o BatchMode=yes" \
            "${sources[@]}" \
            "$rsync_dest"
    fi
}

transport_pull() {
    local args=("$@")
    local local_dest="${args[-1]}"
    local remote_sources=("${args[@]:0:${#args[@]}-1}")

    log_info "Получение файлов с off-site (dest: $local_dest)..."
    for src in "${remote_sources[@]}"; do
        log_info "  <- $(basename "$src")"
    done

    mkdir -p "$local_dest"

    if is_local_offsite; thenи
        rsync \
            $(_rsync_base_flags) \
            "${remote_sources[@]}" \
            "${local_dest}/"
    else
        local rsync_sources=()
        for src in "${remote_sources[@]}"; do
            rsync_sources+=("$(_remote_path "$src")")
        done

        rsync \
            $(_rsync_base_flags) \
            --rsh="ssh -i ${OFFSITE_SSH_KEY} \
                       -o ConnectTimeout=30 \
                       -o BatchMode=yes" \
            "${rsync_sources[@]}" \
            "${local_dest}/"
    fi
}

transport_verify_md5() {
    local remote_archive="$1"
    local archive_name
    archive_name="$(basename "$remote_archive")"
    local remote_dir
    remote_dir="$(dirname "$remote_archive")"

    log_info "Проверка MD5 на off-site: $archive_name"

    transport_exec "cd '${remote_dir}' && md5sum --check --status '${archive_name}.md5'"
}

transport_remove() {
    local files=("$@")

    local cmd="rm -f"
    for f in "${files[@]}"; do
        cmd+=" '${f}'"
    done

    transport_exec "$cmd"
}

transport_list_archives() {
    transport_exec \
        "find '${OFFSITE_DIR}' -maxdepth 1 \
            -name '${ARCHIVE_PREFIX}_*.tar.gz' | sort"
}
