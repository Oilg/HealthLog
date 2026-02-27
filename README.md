# HealthLog

Сервис для загрузки и анализа данных здоровья (Apple Health и другие источники в будущем).

## Быстрый старт

1. Установи зависимости:
```bash
poetry install --with dev
```

2. Подними БД:
```bash
docker compose up -d db
```

3. Примени миграции:
```bash
poetry run alembic upgrade head
```

4. Запусти приложение:
```bash
poetry run python main.py
```

## Тестовая БД

```bash
make test-db-up
make test-db-down
```
