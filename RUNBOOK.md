# HealthLog Runbook

## Ежедневный запуск (просто и надежно)
Выбран вариант: `cron` + локальный скрипт.

Почему:
- просто настроить;
- не зависит от того, открыт терминал или нет;
- легко смотреть логи.

### Установка ежедневного расписания
```bash
make cron-install
```

По умолчанию запуск каждый день в `07:00`.

### Проверка расписания
```bash
crontab -l
```

### Удаление расписания
```bash
make cron-uninstall
```

## Мониторинг логов
Все записи ежедневного запуска пишутся в:
- `logs/daily_pipeline.log`

Онлайн просмотр:
```bash
make logs-tail
```

Поиск ошибок:
```bash
rg -n "ERROR|Traceback|Exception" logs/daily_pipeline.log
```

## Тестовая БД (изолированно от боевой)
Используй отдельный Postgres на порту `5434`.

Запуск:
```bash
make test-db-up
```

Остановка:
```bash
make test-db-down
```

Сброс с удалением данных:
```bash
make test-db-reset
```

Логи тестовой БД:
```bash
make test-db-logs
```

Пример `local.test.env`:
```env
POSTGRES_DSN=postgresql://admin:root@localhost:5434/postgres
PG_LOG_QUERIES=false
```
