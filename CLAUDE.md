# HealthLog Backend — правила работы

## Ветки

- Перед началом любой задачи проверить наличие активной невмерженной ветки (`git branch -a`, `gh pr list`).
- Если активной ветки нет — создать новую от `master`:
  ```bash
  git checkout master && git pull origin master
  git checkout -b feat/<название>   # или fix/, test/, chore/
  ```
- Одна задача — одна ветка. Изменения напрямую в `master` запрещены.

## Workflow после выполнения задачи

### 1. Ревью (`/review`)

Запустить `/review` на текущей ветке. Если ревью нашло замечания — исправить, затем снова `/review`. Повторять до чистого ревью.

### 2. Локальные проверки

После чистого ревью прогнать все три проверки. При любой ошибке — исправить, снова `/review`, снова проверки:

```bash
# Линтер + форматирование
poetry run ruff check . --fix && poetry run ruff format .

# Типизация
poetry run mypy health_log

# Тесты
poetry run pytest -q
```

### 3. Коммит и пуш

Только после зелёных проверок:

```bash
git add <конкретные файлы>
git commit -m "feat/fix/test/chore: описание"
git push origin <ветка>
```

### 4. Pull Request

```bash
gh pr create --title "..." --body "..."
```

### 5. Пайплайн CI

Дождаться завершения всех джобов (Ruff, Tests, Mypy):

```bash
gh run list --repo Oilg/HealthLog --limit 3
gh run view <run-id> --log-failed   # если упало
```

Если джоб упал — исправить локально, повторить шаги 1–4, дождаться нового CI.

### 6. Мерж

Только когда CI полностью зелёный:

```bash
gh pr merge --merge --delete-branch
```

### 7. Деплой

После мержа автоматически запускается `Deploy to production`. Дождаться завершения:

```bash
gh run list --repo Oilg/HealthLog --limit 2
gh run view <run-id> --log-failed   # если упало
```

Если деплой упал — проанализировать логи, исправить, запушить фикс в новую ветку, повторить с шага 1.

## Тесты

- После добавления нового кода — добавить тесты. Тесты не опциональны.
- Структура: `tests/unit/` для unit-тестов, `tests/` для интеграционных.
