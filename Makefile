.PHONY: test-db-up test-db-down test-db-reset test-db-logs cron-install cron-uninstall logs-tail run-daily

TEST_COMPOSE=docker compose -p healthlog_test -f docker-compose.test.yml

test-db-up:
	$(TEST_COMPOSE) up -d --remove-orphans

test-db-down:
	$(TEST_COMPOSE) down --remove-orphans

test-db-reset:
	$(TEST_COMPOSE) down -v --remove-orphans
	$(TEST_COMPOSE) up -d --remove-orphans

test-db-logs:
	$(TEST_COMPOSE) logs -f db_test

cron-install:
	bash scripts/install_daily_cron.sh

cron-uninstall:
	bash scripts/uninstall_daily_cron.sh

logs-tail:
	tail -f logs/daily_pipeline.log

run-daily:
	bash scripts/daily_pipeline.sh
