# NFS Connect

Кроссплатформенное приложение для автоматизированного подключения к VPN и монтирования сетевой файловой системы NFS с автоматической установкой системных зависимостей.

## Описание

NFS Connect - это приложение, которое упрощает доступ к сетевому хранилищу через VPN-соединения. Приложение автоматизирует:

- Установление соединения OpenVPN
- SSH-аутентификацию для конфигурации пользователя
- Автоматическую синхронизацию GID с сервера
- Монтирование файловой системы NFS
- Управление разрешениями доступа
- Установку системных зависимостей

Поддерживаемые платформы: Windows, Linux, macOS

## Основные возможности

### Базовая функциональность

- Однокликовое подключение к VPN и монтированию NFS
- Кроссплатформенная совместимость (Windows, Linux, macOS)
- Командные файлы и графический интерфейс PyQt5
- Мониторинг состояния в режиме реального времени
- Автоматическое управление VPN соединением
- Корректное определение разрешений NFS через синхронизацию GID

### Управление системой

- Автоматическая установка NFS Client на Windows
- Автоматическая установка OpenVPN на всех платформах
- Linux: автоматическая установка nfs-common
- macOS: установка инструментов NFS через Homebrew
- Автоматическая проверка системных зависимостей

## Требования к системе

### Windows

- Windows 10 или после
- Python 3.8+
- OpenVPN (автоустановка)
- NFS Client (автоустановка)
- Права администратора для первого запуска

### Linux

- Ubuntu 18.04+ или эквивалент
- Python 3.8+
- OpenVPN (автоустановка через apt)
- nfs-common (автоустановка через apt)
- Доступ судо для монтирования NFS

### macOS

- macOS 10.14+
- Python 3.8+
- Homebrew (для установки OpenVPN)
- OpenVPN (автоустановка через Homebrew)
- Нативная поддержка инструментов NFS

## Установка

### Способ 1: Установка из исходного кода

1. Клонировать репозиторий:
```bash
git clone https://github.com/ALEXxXANDR24/nfs_app.git
cd nfs_app
```

2. Создать виртуальное окружение:
```bash
python -m venv venv
```

3. Активировать окружение:

На Windows (PowerShell):
```powershell
.\venv\Scripts\Activate.ps1
```

На Windows (Командная строка):
```cmd
.\venv\Scripts\activate.bat
```

На Linux/macOS:
```bash
source venv/bin/activate
```

4. Установить зависимости:
```bash
pip install -r requirements.txt
```

5. Запустить приложение:
```bash
python -m nfs_vpn_app.main
```

### Способ 2: Представленные исполняемые файлы

От строительных файлов доступны:
- Windows: NFS_Connect.exe
- Linux: исполняемый файл run.sh
- macOS: исполняемый файл run.sh

## Конфигурация

### Переменные окружения

Конфигурация управляется через файл `.env`. Скопируйте из шаблона:

```bash
cp .env.example .env
```

Отредактируйте .env в текстовом редакторе и обновите:

## Использование

### Запуск приложения

На Windows:
```bash
python -m nfs_vpn_app.main
```

На Linux/macOS:
```bash
python3 -m nfs_vpn_app.main
```

Или запустите предоставленный исполняемый файл напрямую.

### Рабочий процесс пользователя

1. Запустите приложение
2. Введите электронную почту HSE и пароль в диалоге входа
3. Приложение автоматически:
   - Подключается к VPN
   - Устанавливает SSH-соединение
   - Синхронизирует GID с сервера
   - Монтирует общую папку NFS
4. Доступ к файлам через точку монтирования:
   - Windows: Буква диска (например, Z:)
   - Linux: ~/nfs_share (по умолчанию)
   - macOS: ~/nfs (по умолчанию)
5. Используйте файлы как если бы они были локальными
6. Приложение можно минимизировать; NFS остается смонтированным
7. Нажмите отключить для отмонтирования и закрытия VPN

### Поиск и устранение неисправностей

#### "Ошибка подключения VPN"

- Проверьте интернет-соединение
- Проверьте наличие OpenVPN: `openvpn --version`
- Проверьте наличие файла конфигурации VPN
- Проверьте разрешение брандмауэра для OpenVPN


#### "Ошибка монтирования NFS"

- Проверьте подключение VPN (пинг)
- Проверьте доступность сервера NFS
- Убедитесь в существовании точки монтирования
- На Linux/macOS: Проверьте разрешения sudo
- Проверьте разрешения экспорта NFS на сервере

## File Organization

```
nfs_app/
├── nfs_vpn_app/                          Main application
│   ├── main.py                           Application entry point
│   ├── ui/
│   │   ├── main_window.py                Main GUI window
│   │   └── login_dialog.py               Login dialog
│   ├── core/
│   │   ├── logger.py                     Logging system
│   │   ├── config_manager.py             Configuration management
│   │   ├── ssh_client.py                 SSH connections
│   │   ├── vpn_manager.py                VPN management
│   │   ├── nfs_manager.py                NFS mounting
│   │   └── system_gid_manager.py         GID synchronization
│   ├── platform_specific/
│   │   ├── windows.py                    Windows-specific operations
│   │   ├── linux.py                      Linux-specific operations
│   │   └── macos.py                      macOS-specific operations
│   ├── utils/
│   │   ├── process_runner.py             Process execution utilities
│   │   └── validators.py                 Input validation
│   └── resources/
│       └── vpn_config.ovpn               VPN configuration
├── .env.example                          Configuration template
├── .env                                  Local configuration (not versioned)
├── requirements.txt                      Python dependencies
└── README.md                             This file
```

## Архитектура

Приложение следует модульной архитектуре:

### Основные компоненты

- **Точка входа (main.py)**: Инициализация приложения и GUI
- **Графический интерфейс (ui/)**: Компоненты PyQt5
- **Бизнес-логика (core/)**: Управление VPN, NFS, SSH и GID
- **Платформа-абстракция (platform_specific/)**: ОП-специфичные реализации
- **Утилиты (utils/)**: Вспомогательные функции и остальные валидаторы

### Поток данных

```
Вход пользователя
  -> SSH подключение к серверу
  -> Получение GID с сервера
  -> Проверка подключения VPN
  -> Локальная синхронизация GID
  -> Операция монтирования NFS
  -> Доступ к файлам
```

## Разработка

### Установка проекта

```bash
git clone https://github.com/ALEXxXANDR24/nfs_app.git
cd nfs_app
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
