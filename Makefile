.PHONY: test-db-up test-db-down test-db-reset test-db-logs cron-install cron-uninstall logs-tail run-daily

test-db-up:
	docker compose -f docker-compose.test.yml up -d

test-db-down:
	docker compose -f docker-compose.test.yml down

test-db-reset:
	docker compose -f docker-compose.test.yml down -v
	docker compose -f docker-compose.test.yml up -d

test-db-logs:
	docker compose -f docker-compose.test.yml logs -f db_test

cron-install:
	bash scripts/install_daily_cron.sh

cron-uninstall:
	bash scripts/uninstall_daily_cron.sh

logs-tail:
	tail -f logs/daily_pipeline.log

run-daily:
	bash scripts/daily_pipeline.sh
