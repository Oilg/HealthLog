import asyncio
import json

from health_log.analysis import HealthRiskAnalyzer, serialize_assessment
from health_log.db import engine


async def main():
    async with engine.begin() as conn:
        analyzer = HealthRiskAnalyzer(conn)
        report = await analyzer.analyze_all_windows()

    output = {}
    for window, payload in report.items():
        output[window.value] = {
            "start": payload["start"].isoformat(),
            "end": payload["end"].isoformat(),
            "inserted_sleep_apnea_events": payload["inserted_sleep_apnea_events"],
            "assessments": [serialize_assessment(item) for item in payload["assessments"]],
        }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
