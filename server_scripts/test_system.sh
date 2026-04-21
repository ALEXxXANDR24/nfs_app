#!/usr/bin/env bash
# /opt/testing/test_system.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_LOG_DIR="/opt/testing/logs"
TEST_RESULTS_DIR="/opt/testing/results"

mkdir -p "$TEST_LOG_DIR"
mkdir -p "$TEST_RESULTS_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TEST_LOG="${TEST_LOG_DIR}/test_${TIMESTAMP}.log"

TEST_USER="test_student"
TEST_GID="3001"
TEST_MOUNT_POINT="/tmp/nfs_test_mount"
NFS_SERVER="localhost"

declare -a FILE_SIZES=(1 10 50 100)

MAX_CLIENTS=10

log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[${timestamp}] [${level}] ${message}" | tee -a "$TEST_LOG"
}

log_info() {
    echo -e "[INFO]${NC} $*" | tee -a "$TEST_LOG"
}

log_ok() {
    echo -e "[OK]${NC} $*" | tee -a "$TEST_LOG"
}

log_warn() {
    echo -e "[WARN]${NC} $*" | tee -a "$TEST_LOG"
}

log_error() {
    echo -e "[ERROR]${NC} $*" | tee -a "$TEST_LOG"
}

log_section() {
    echo "" | tee -a "$TEST_LOG"
    echo "================================" | tee -a "$TEST_LOG"
    echo "$*" | tee -a "$TEST_LOG"
    echo "================================" | tee -a "$TEST_LOG"
}

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Скрипт должен быть запущен с правами root"
        exit 1
    fi
}

nfs_write() {
    local file="$1"
    local content="$2"

    echo "$content" | runuser -u root -g "$TEST_USER" -- tee "$file" > /dev/null 2>&1
}

nfs_append() {
    local file="$1"
    local content="$2"

    echo "$content" | runuser -u root -g "$TEST_USER" -- tee -a "$file" > /dev/null 2>&1
}

nfs_mkdir() {
    local dir="$1"

    runuser -u root -g "$TEST_USER" -- mkdir -p "$dir" 2>/dev/null
}

nfs_rm() {
    local path="$1"

    runuser -u root -g "$TEST_USER" -- rm -rf "$path" 2>/dev/null
}

nfs_cp() {
    local src="$1"
    local dst="$2"

    runuser -u root -g "$TEST_USER" -- cp "$src" "$dst" 2>/dev/null
}

nfs_cat() {
    local file="$1"

    runuser -u root -g "$TEST_USER" -- cat "$file" 2>/dev/null
}

setup_test_environment() {
    log_info "Настройка тестового окружения..."

    mkdir -p "$TEST_MOUNT_POINT"

    if ! mountpoint -q "$TEST_MOUNT_POINT" 2>/dev/null; then
        log_info "Монтирование NFS..."
        if mount -t nfs4 -o vers=4.2,port=2049 \
            "${NFS_SERVER}:/" "$TEST_MOUNT_POINT" 2>/dev/null; then
            log_ok "NFS успешно смонтирован"
        else
            log_error "Ошибка монтирования NFS"
            exit 1
        fi
    else
        log_info "NFS уже смонтирован"
    fi

    if [[ -d "${TEST_MOUNT_POINT}/${TEST_USER}" ]]; then
        log_info "Очистка предыдущих тестовых файлов..."
        runuser -u root -g "$TEST_USER" -- find "${TEST_MOUNT_POINT}/${TEST_USER}" -mindepth 1 -delete 2>/dev/null || true
    fi

    log_ok "Тестовое окружение готово"
}

cleanup_test_environment() {
    log_info "Очистка тестового окружения..."

    if [[ -d "${TEST_MOUNT_POINT}/${TEST_USER}" ]]; then
        runuser -u root -g "$TEST_USER" -- find "${TEST_MOUNT_POINT}/${TEST_USER}" -mindepth 1 -delete 2>/dev/null || true
    fi

    if mountpoint -q "$TEST_MOUNT_POINT" 2>/dev/null; then
        umount -f "$TEST_MOUNT_POINT" 2>/dev/null || true
        log_info "NFS размонтирован"
    fi

    if [[ -d "$TEST_MOUNT_POINT" ]]; then
        rm -rf "$TEST_MOUNT_POINT" 2>/dev/null || true
    fi

    rm -f /tmp/source_*.dat 2>/dev/null || true

    log_ok "Тестовое окружение очищено"
}

generate_test_file() {
    local file_path="$1"
    local size_mb="$2"

    dd if=/dev/urandom of="$file_path" bs=1M count="$size_mb" status=none 2>/dev/null
}

calculate_md5() {
    local file="$1"
    md5sum "$file" 2>/dev/null | awk '{print $1}'
}

# ============================================================================
# ТЕСТ 1: БАЗОВЫЕ ОПЕРАЦИИ С ФАЙЛАМИ
# ============================================================================

test_basic_operations() {
    log_section "ТЕСТ 1: Базовые операции с файлами"

    local result=0
    local test_file="${TEST_MOUNT_POINT}/${TEST_USER}/test_file.txt"
    local test_dir="${TEST_MOUNT_POINT}/${TEST_USER}/test_directory"

    log_info "Тест: создание файла..."
    local start_time
    start_time=$(date +%s.%N)
    if nfs_write "$test_file" "Test content"; then
        local end_time
        end_time=$(date +%s.%N)
        local elapsed
        elapsed=$(echo "$end_time - $start_time" | bc)
        log_ok "Файл создан (${elapsed}s)"
    else
        log_error "Ошибка создания файла"
        result=1
    fi

    log_info "Тест: чтение файла..."
    start_time=$(date +%s.%N)
    if nfs_cat "$test_file" | grep -q "Test content"; then
        end_time=$(date +%s.%N)
        elapsed=$(echo "$end_time - $start_time" | bc)
        log_ok "Файл прочитан (${elapsed}s)"
    else
        log_error "Ошибка чтения файла"
        result=1
    fi

    log_info "Тест: редактирование файла..."
    start_time=$(date +%s.%N)
    if nfs_append "$test_file" "Modified content"; then
        end_time=$(date +%s.%N)
        elapsed=$(echo "$end_time - $start_time" | bc)
        log_ok "Файл изменён (${elapsed}s)"
    else
        log_error "Ошибка изменения файла"
        result=1
    fi

    log_info "Тест: создание директории..."
    start_time=$(date +%s.%N)
    if nfs_mkdir "$test_dir"; then
        end_time=$(date +%s.%N)
        elapsed=$(echo "$end_time - $start_time" | bc)
        log_ok "Директория создана (${elapsed}s)"
    else
        log_error "Ошибка создания директории"
        result=1
    fi

    log_info "Тест: удаление файла..."
    start_time=$(date +%s.%N)
    if nfs_rm "$test_file"; then
        end_time=$(date +%s.%N)
        elapsed=$(echo "$end_time - $start_time" | bc)
        log_ok "Файл удалён (${elapsed}s)"
    else
        log_error "Ошибка удаления файла"
        result=1
    fi

    log_info "Тест: удаление директории..."
    start_time=$(date +%s.%N)
    if nfs_rm "$test_dir"; then
        end_time=$(date +%s.%N)
        elapsed=$(echo "$end_time - $start_time" | bc)
        log_ok "Директория удалена (${elapsed}s)"
    else
        log_error "Ошибка удаления директории"
        result=1
    fi

    return $result
}

# ============================================================================
# ТЕСТ 2: ПРОИЗВОДИТЕЛЬНОСТЬ - СКОРОСТЬ ОПЕРАЦИЙ
# ============================================================================

test_file_operations_speed() {
    log_section "ТЕСТ 2: Скорость операций чтения/записи"

    local result=0
    local results_file="${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"

    echo "=========================================" > "$results_file"
    echo "РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ ПРОИЗВОДИТЕЛЬНОСТИ" >> "$results_file"
    echo "=========================================" >> "$results_file"
    echo "Дата: $(date)" >> "$results_file"
    echo "Сервер: $NFS_SERVER" >> "$results_file"
    echo "" >> "$results_file"

    for size in "${FILE_SIZES[@]}"; do
        log_info "Тестирование с файлом ${size}MB..."

        local test_file="${TEST_MOUNT_POINT}/${TEST_USER}/perf_test_${size}MB.dat"
        local source_file="/tmp/source_${size}MB.dat"

        log_info "  Генерация тестового файла ${size}MB..."
        generate_test_file "$source_file" "$size"
        local source_md5
        source_md5=$(calculate_md5 "$source_file")

        log_info "  Тест записи ${size}MB..."
        local start_time
        start_time=$(date +%s.%N)

        nfs_cp "$source_file" "$test_file"

        local end_time
        end_time=$(date +%s.%N)
        local write_time
        write_time=$(echo "$end_time - $start_time" | bc)

        if [[ $(echo "$write_time < 0.001" | bc) -eq 1 ]]; then
            write_time="0.001"
        fi

        local write_speed
        write_speed=$(echo "scale=2; $size / $write_time" | bc)

        log_ok "  Запись ${size}MB: ${write_time}s (${write_speed} MB/s)"
        echo "Запись ${size}MB: ${write_time}s (${write_speed} MB/s)" >> "$results_file"

        sync
        echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true

        log_info "  Тест чтения ${size}MB..."
        start_time=$(date +%s.%N)

        nfs_cat "$test_file" > /dev/null

        end_time=$(date +%s.%N)
        local read_time
        read_time=$(echo "$end_time - $start_time" | bc)

        if [[ $(echo "$read_time < 0.001" | bc) -eq 1 ]]; then
            read_time="0.001"
        fi

        local read_speed
        read_speed=$(echo "scale=2; $size / $read_time" | bc)

        log_ok "  Чтение ${size}MB: ${read_time}s (${read_speed} MB/s)"
        echo "Чтение ${size}MB: ${read_time}s (${read_speed} MB/s)" >> "$results_file"

        local dest_md5
        dest_md5=$(runuser -u root -g "$TEST_USER" -- md5sum "$test_file" 2>/dev/null | awk '{print $1}')

        if [[ "$source_md5" == "$dest_md5" ]]; then
            log_ok "  MD5 совпадает - данные не повреждены"
            echo "MD5: OK" >> "$results_file"
        else
            log_error "  MD5 НЕ совпадает - возможно повреждение данных"
            log_error "  Источник: $source_md5"
            log_error "  Назначение: $dest_md5"
            echo "MD5: FAILED" >> "$results_file"
            result=1
        fi

        nfs_rm "$test_file"
        rm -f "$source_file"

        echo "" >> "$results_file"
    done

    log_info "Результаты сохранены в: $results_file"

    return $result
}

# ============================================================================
# ТЕСТ 3: ПРОИЗВОДИТЕЛЬНОСТЬ - ЗАДЕРЖКА ОПЕРАЦИЙ
# ============================================================================

test_latency() {
    log_section "ТЕСТ 3: Задержка операций (latency)"

    local result=0
    local iterations=100
    local total_time=0

    log_info "Измерение задержки создания/удаления файлов ($iterations итераций)..."

    for ((i=1; i<=iterations; i++)); do
        local test_file="${TEST_MOUNT_POINT}/${TEST_USER}/latency_test_${i}.txt"

        local start_time
        start_time=$(date +%s.%N)

        nfs_write "$test_file" "test"
        nfs_rm "$test_file"

        local end_time
        end_time=$(date +%s.%N)

        local op_time
        op_time=$(echo "$end_time - $start_time" | bc)
        total_time=$(echo "$total_time + $op_time" | bc)
    done

    local avg_latency
    avg_latency=$(echo "scale=6; $total_time / $iterations" | bc)
    local avg_latency_ms
    avg_latency_ms=$(echo "scale=2; $avg_latency * 1000" | bc)

    log_ok "Средняя задержка: ${avg_latency_ms}ms"
    echo "" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "Задержка операций:" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "  Итераций: $iterations" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "  Средняя задержка: ${avg_latency_ms}ms" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"

    return $result
}

# ============================================================================
# ТЕСТ 4: ПРОИЗВОДИТЕЛЬНОСТЬ - ОПЕРАЦИИ С МНОЖЕСТВОМ ФАЙЛОВ
# ============================================================================

test_many_small_files() {
    log_section "ТЕСТ 4: Операции с множеством мелких файлов"

    local result=0
    local file_count=1000
    local test_dir="${TEST_MOUNT_POINT}/${TEST_USER}/many_files_test"

    nfs_mkdir "$test_dir"

    log_info "Создание $file_count файлов..."
    local start_time
    start_time=$(date +%s.%N)

    for ((i=1; i<=file_count; i++)); do
        nfs_write "${test_dir}/file_${i}.txt" "Content $i" 2>/dev/null
    done

    local end_time
    end_time=$(date +%s.%N)
    local create_time
    create_time=$(echo "$end_time - $start_time" | bc)
    local files_per_sec
    files_per_sec=$(echo "scale=2; $file_count / $create_time" | bc)

    log_ok "Создано $file_count файлов за ${create_time}s (${files_per_sec} файлов/сек)"

    log_info "Чтение $file_count файлов..."
    start_time=$(date +%s.%N)

    for ((i=1; i<=file_count; i++)); do
        nfs_cat "${test_dir}/file_${i}.txt" > /dev/null 2>/dev/null
    done

    end_time=$(date +%s.%N)
    local read_time
    read_time=$(echo "$end_time - $start_time" | bc)
    files_per_sec=$(echo "scale=2; $file_count / $read_time" | bc)

    log_ok "Прочитано $file_count файлов за ${read_time}s (${files_per_sec} файлов/сек)"

    log_info "Удаление $file_count файлов..."
    start_time=$(date +%s.%N)

    nfs_rm "$test_dir"

    end_time=$(date +%s.%N)
    local delete_time
    delete_time=$(echo "$end_time - $start_time" | bc)
    files_per_sec=$(echo "scale=2; $file_count / $delete_time" | bc)

    log_ok "Удалено $file_count файлов за ${delete_time}s (${files_per_sec} файлов/сек)"

    echo "" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "Операции с множеством файлов ($file_count файлов):" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "  Создание: ${create_time}s ($(echo "scale=2; $file_count / $create_time" | bc) файлов/сек)" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "  Чтение:   ${read_time}s ($(echo "scale=2; $file_count / $read_time" | bc) файлов/сек)" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "  Удаление: ${delete_time}s ($(echo "scale=2; $file_count / $delete_time" | bc) файлов/сек)" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"

    return $result
}

# ============================================================================
# ТЕСТ 5: МНОГОПОЛЬЗОВАТЕЛЬСКИЙ - ПАРАЛЛЕЛЬНАЯ РАБОТА КЛИЕНТОВ
# ============================================================================

test_parallel_clients() {
    log_section "ТЕСТ 5: Параллельная работа клиентов"

    local result=0

    log_info "Тестирование с $MAX_CLIENTS параллельными клиентами..."

    simulate_client() {
        local client_id=$1
        local client_dir="${TEST_MOUNT_POINT}/${TEST_USER}/client_${client_id}"

        runuser -u root -g "$TEST_USER" -- bash -c "
            mkdir -p '$client_dir'
            for i in {1..20}; do
                echo 'Client $client_id - operation \$i - $(date +%s.%N)' > '${client_dir}/file_\${i}.txt'
                cat '${client_dir}/file_\${i}.txt' > /dev/null
            done
            rm -rf '$client_dir'
        " 2>/dev/null
    }

    local start_time
    start_time=$(date +%s.%N)

    for ((client=1; client<=MAX_CLIENTS; client++)); do
        simulate_client "$client" &
    done

    wait

    local end_time
    end_time=$(date +%s.%N)
    local total_time
    total_time=$(echo "$end_time - $start_time" | bc)

    local operations_total=$((MAX_CLIENTS * 20 * 3))
    local ops_per_sec
    ops_per_sec=$(echo "scale=2; $operations_total / $total_time" | bc)

    log_ok "$MAX_CLIENTS клиентов обработаны за ${total_time}s"
    log_ok "Всего операций: $operations_total (${ops_per_sec} операций/сек)"

    echo "" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "Параллельная работа клиентов:" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "  Клиентов: $MAX_CLIENTS" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "  Время выполнения: ${total_time}s" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "  Операций на клиента: 60 (20 файлов × 3 операции)" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "  Всего операций: $operations_total" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "  Производительность: ${ops_per_sec} операций/сек" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"

    return $result
}

# ============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================================

run_all_tests() {
    local total_tests=0
    local passed_tests=0
    local failed_tests=0

    log_section "ТЕСТИРОВАНИЕ ПРОИЗВОДИТЕЛЬНОСТИ И КОРРЕКТНОСТИ СИСТЕМЫ NFS"
    log_info "Время начала: $(date)"
    log_info "Лог: $TEST_LOG"
    log_info "Тестовый пользователь: $TEST_USER (GID: $TEST_GID)"

    setup_test_environment

    declare -a tests=(
        "test_basic_operations:Базовые операции с файлами"
        "test_file_operations_speed:Скорость чтения/записи"
        "test_latency:Задержка операций"
        "test_many_small_files:Операции с множеством файлов"
        "test_parallel_clients:Параллельная работа клиентов"
    )

    for test_entry in "${tests[@]}"; do
        IFS=':' read -r test_func test_name <<< "$test_entry"

        total_tests=$((total_tests + 1))

        if $test_func; then
            passed_tests=$((passed_tests + 1))
            log_ok "$test_name - PASSED"
        else
            failed_tests=$((failed_tests + 1))
            log_error "$test_name - FAILED"
        fi

        echo ""
    done

    cleanup_test_environment

    log_section "РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ"
    log_info "Всего тестов:    $total_tests"
    log_ok   "Успешно:         $passed_tests"

    if [[ $failed_tests -gt 0 ]]; then
        log_error "Провалено:       $failed_tests"
    else
        log_info "Провалено:       $failed_tests"
    fi

    local success_rate
    success_rate=$(echo "scale=2; $passed_tests * 100 / $total_tests" | bc)
    log_info "Процент успеха:  ${success_rate}%"

    log_info ""
    log_info "Время окончания: $(date)"
    log_info "Лог сохранён:    $TEST_LOG"
    log_info "Результаты:      ${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"

    echo "" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "=========================================" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "ИТОГО:" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "  Всего тестов: $total_tests" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "  Успешно: $passed_tests" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "  Провалено: $failed_tests" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "  Процент успеха: ${success_rate}%" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"
    echo "=========================================" >> "${TEST_RESULTS_DIR}/performance_${TIMESTAMP}.txt"

    if [[ $failed_tests -eq 0 ]]; then
        log_ok "ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!"
        return 0
    else
        log_error "НЕКОТОРЫЕ ТЕСТЫ ПРОВАЛЕНЫ!"
        return 1
    fi
}

# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

main() {
    check_root
    run_all_tests
    exit $?
}

main "$@"
