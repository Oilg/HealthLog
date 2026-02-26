from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import xml.etree.ElementTree as ET


DATE_FORMATS = ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S")


@dataclass(slots=True)
class ParsedRecord:
    attrs: dict[str, str]
    metadata: dict[str, str] = field(default_factory=dict)
    hrv_bpm: list[dict[str, str]] = field(default_factory=list)

    @property
    def record_type(self) -> str:
        return self.attrs.get("type", "")


def parse_datetime(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    cleaned = dt_str.replace("\u00A0", " ").strip()
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    return None


class AppleHealthXmlParser:
    @staticmethod
    def parse_xml_content(xml_content: str) -> list[ParsedRecord]:
        root = ET.fromstring(xml_content)
        records: list[ParsedRecord] = []

        for rec in root.findall("Record"):
            attrs = dict(rec.attrib)
            metadata: dict[str, str] = {}
            bpm_entries: list[dict[str, str]] = []

            for child in rec:
                if child.tag == "MetadataEntry":
                    key = child.attrib.get("key")
                    value = child.attrib.get("value")
                    if key and value is not None:
                        metadata[key] = value
                elif child.tag == "HeartRateVariabilityMetadataList":
                    for bpm_node in child.findall("InstantaneousBeatsPerMinute"):
                        bpm = bpm_node.attrib.get("bpm")
                        bpm_time = bpm_node.attrib.get("time")
                        if bpm and bpm_time:
                            bpm_entries.append({"bpm": bpm, "time": bpm_time})

            records.append(ParsedRecord(attrs=attrs, metadata=metadata, hrv_bpm=bpm_entries))

        return records

    @staticmethod
    def parse_xml_file(file_path: str) -> list[ParsedRecord]:
        with open(file_path, "r", encoding="utf-8") as f:
            return AppleHealthXmlParser.parse_xml_content(f.read())
