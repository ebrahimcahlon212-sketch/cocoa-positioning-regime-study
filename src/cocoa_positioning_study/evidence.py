"""Structured scientific evidence and explicit translation guardrails."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

EVIDENCE_PATH: Final = Path("data/raw/scientific-cocoa-evidence-registry.csv")
GUARDRAILS_PATH: Final = Path("data/derived/evidence_guardrails.json")


def _utc(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp is not timezone-aware: {raw}")
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    citation_short: str
    title: str
    authors: str
    publication_date: date
    journal: str
    doi: str
    source_url: str
    source_sha256: str
    retrieved_at_utc: datetime
    geography: str
    study_type: str
    sample_or_data: str
    exposure: str
    lag: str
    reported_result: str
    mechanism_use: str
    signal_keys: tuple[str, ...]
    evidence_grade: str
    external_validity_limits: str
    open_access_license: str


def load_evidence_registry(root: Path) -> tuple[EvidenceRecord, ...]:
    path = root / EVIDENCE_PATH
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("scientific evidence registry is empty")
    records: list[EvidenceRecord] = []
    seen: set[str] = set()
    allowed_grades = {
        "natural_experiment",
        "observational_panel",
        "observational_gradient",
        "model_projection",
    }
    for raw in rows:
        record = EvidenceRecord(
            evidence_id=raw["evidence_id"],
            citation_short=raw["citation_short"],
            title=raw["title"],
            authors=raw["authors"],
            publication_date=date.fromisoformat(raw["publication_date"]),
            journal=raw["journal"],
            doi=raw["doi"],
            source_url=raw["source_url"],
            source_sha256=raw["source_sha256"],
            retrieved_at_utc=_utc(raw["retrieved_at_utc"]),
            geography=raw["geography"],
            study_type=raw["study_type"],
            sample_or_data=raw["sample_or_data"],
            exposure=raw["exposure"],
            lag=raw["lag"],
            reported_result=raw["reported_result"],
            mechanism_use=raw["mechanism_use"],
            signal_keys=tuple(value for value in raw["signal_keys"].split(";") if value),
            evidence_grade=raw["evidence_grade"],
            external_validity_limits=raw["external_validity_limits"],
            open_access_license=raw["open_access_license"],
        )
        if record.evidence_id in seen:
            raise ValueError(f"duplicate scientific evidence record: {record.evidence_id}")
        seen.add(record.evidence_id)
        if not record.doi.startswith("10.") or not record.source_url.startswith("https://"):
            raise ValueError(f"invalid DOI or source URL: {record.evidence_id}")
        if len(record.source_sha256) != 64:
            raise ValueError(f"invalid source SHA-256: {record.evidence_id}")
        if record.publication_date > record.retrieved_at_utc.date():
            raise ValueError(f"evidence publication is after retrieval: {record.evidence_id}")
        if record.evidence_grade not in allowed_grades:
            raise ValueError(f"unknown evidence grade: {record.evidence_id}")
        if not record.signal_keys:
            raise ValueError(f"evidence record has no signal keys: {record.evidence_id}")
        records.append(record)
    return tuple(sorted(records, key=lambda item: (item.publication_date, item.evidence_id)))


def evidence_for_signal(
    records: tuple[EvidenceRecord, ...], signal_key: str
) -> tuple[EvidenceRecord, ...]:
    return tuple(record for record in records if signal_key in record.signal_keys)


def build_evidence_guardrails(records: tuple[EvidenceRecord, ...]) -> dict[str, Any]:
    if not records:
        raise ValueError("scientific guardrails require at least one evidence record")
    signal_index = {
        signal: [record.evidence_id for record in records if signal in record.signal_keys]
        for signal in sorted({signal for record in records for signal in record.signal_keys})
    }
    return {
        "as_of_utc": max(record.retrieved_at_utc for record in records)
        .isoformat()
        .replace("+00:00", "Z"),
        "record_count": len(records),
        "signal_index": signal_index,
        "records": [
            {
                **asdict(record),
                "publication_date": record.publication_date.isoformat(),
                "retrieved_at_utc": record.retrieved_at_utc.isoformat().replace("+00:00", "Z"),
                "signal_keys": list(record.signal_keys),
            }
            for record in records
        ],
        "translation_guardrails": [
            "Treat rainfall as non-monotonic: drought can damage cocoa, while excess rain and humidity can raise fungal-disease pressure.",
            "Apply crop-stage and lag logic; Ghana pod observations found strongest climate associations at fruit set with one-to-five-month lags by pod class.",
            "Do not transfer the magnitude of an extreme Bahia drought loss directly to Ghana or Cote d'Ivoire.",
            "Do not convert a grid-cell weather anomaly to production tonnes without crop-area weights, phenology, farm management, disease, and validated yield response.",
            "Observational and model-projection studies provide mechanism priors, not proof that a weather reading caused a market move or predicts returns.",
        ],
    }


def build_evidence_outputs(root: Path) -> dict[Path, bytes]:
    payload = (
        json.dumps(
            build_evidence_guardrails(load_evidence_registry(root)),
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
        )
        + "\n"
    )
    return {root / GUARDRAILS_PATH: payload.encode("utf-8")}


def materialize_evidence(root: Path, *, check: bool = False) -> None:
    mismatches: list[str] = []
    for path, payload in build_evidence_outputs(root).items():
        if check:
            if not path.exists() or path.read_bytes() != payload:
                mismatches.append(str(path.relative_to(root)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    if mismatches:
        raise ValueError("derived evidence outputs are stale: " + ", ".join(mismatches))
