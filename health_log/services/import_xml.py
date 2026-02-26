import asyncio
from pathlib import Path

from health_log.db import engine
from health_log.services.ingestion import ingest_xml_file


DEFAULT_XML_PATH = Path(__file__).with_name("watchData.xml")


async def async_main(file_path: str | None = None):
    target_path = Path(file_path) if file_path else DEFAULT_XML_PATH

    async with engine.begin() as conn:
        result = await ingest_xml_file(conn, str(target_path))

    print(f"upload_id={result.upload_id} is_new_upload={result.is_new_upload}")
    print(f"raw_records={result.raw_records_count}")

    if result.normalized_counts:
        for record_type, count in result.normalized_counts.items():
            print(f"normalized {record_type}: {count}")

    print(f"hrv_records={result.hrv_records_count} hrv_bpm_records={result.hrv_bpm_count}")


if __name__ == "__main__":
    asyncio.run(async_main())
