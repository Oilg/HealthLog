"""Разовая рассылка push с просьбой указать DOB активным пользователям без даты рождения.

Использование:
    poetry run python -m scripts.send_dob_push          # боевой прогон
    poetry run python -m scripts.send_dob_push --dry-run # без отправки, только лог кому пошлём

Критерий выборки: is_active=true AND apns_device_token IS NOT NULL AND date_of_birth IS NULL.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import and_, select

from health_log.db import engine
from health_log.repositories.v1 import tables
from health_log.services.apns import send_dob_request_push

logger = logging.getLogger("send_dob_push")


async def _fetch_targets() -> list[tuple[int, str]]:
    """Возвращает список (user_id, device_token) для рассылки."""
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                select(tables.users.c.id, tables.users.c.apns_device_token).where(
                    and_(
                        tables.users.c.is_active.is_(True),
                        tables.users.c.date_of_birth.is_(None),
                        tables.users.c.apns_device_token.is_not(None),
                    )
                )
            )
        ).all()
    return [(int(r.id), str(r.apns_device_token)) for r in rows]


async def _send_all(targets: list[tuple[int, str]], *, dry_run: bool) -> tuple[int, int]:
    sent = 0
    failed = 0
    for user_id, token in targets:
        masked = token[:8] + "…"
        if dry_run:
            logger.info("[dry-run] user=%d token=%s", user_id, masked)
            sent += 1
            continue
        ok = await send_dob_request_push(token)
        if ok:
            sent += 1
            logger.info("Отправлено: user=%d token=%s", user_id, masked)
        else:
            failed += 1
            logger.warning("Не доставлено: user=%d token=%s", user_id, masked)
    return sent, failed


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Не отправлять, только показать кому послали бы."
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    targets = await _fetch_targets()
    logger.info("Найдено получателей: %d", len(targets))

    if not targets:
        return 0

    sent, failed = await _send_all(targets, dry_run=args.dry_run)
    logger.info("Готово. Отправлено: %d, ошибок: %d", sent, failed)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
