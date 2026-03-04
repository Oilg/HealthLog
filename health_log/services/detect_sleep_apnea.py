import asyncio
import json

from health_log.analysis import HealthRiskAnalyzer, serialize_assessment
from health_log.db import engine
from health_log.repositories.auth import UsersRepository


async def main():
    async with engine.begin() as conn:
        user_ids = await UsersRepository(conn).list_active_user_ids()
        output = {}

        for user_id in user_ids:
            analyzer = HealthRiskAnalyzer(conn, user_id=user_id)
            report = await analyzer.analyze_all_windows()
            output[str(user_id)] = {}
            for window, payload in report.items():
                output[str(user_id)][window.value] = {
                    "start": payload["start"].isoformat(),
                    "end": payload["end"].isoformat(),
                    "inserted_sleep_apnea_events": payload["inserted_sleep_apnea_events"],
                    "assessments": [serialize_assessment(item) for item in payload["assessments"]],
                }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
