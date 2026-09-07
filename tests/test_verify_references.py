import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_references.py"
SPEC = importlib.util.spec_from_file_location("verify_references", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

from verify_references import (
    archived_crossref_metadata_complete,
    message_from_archived_audit,
    year_value,
)


def complete_audit(year="2024"):
    return {
        "crossref_status": "PASS",
        "doi": "10.1234/example",
        "verified_title": "Example title",
        "verified_authors": "Smith, Jane",
        "verified_year": year,
        "verified_journal": "Example Journal",
    }


def complete_bibliography(year="2024"):
    return {
        "year": year,
        "journal_or_publisher": "Example Journal",
        "volume": "2",
        "issue": "1",
        "pages_or_article": "10-20",
    }


def test_archived_metadata_requires_publication_year():
    assert archived_crossref_metadata_complete(complete_audit(), complete_bibliography())
    assert not archived_crossref_metadata_complete(
        complete_audit(year=""), complete_bibliography(year="")
    )


def test_archived_message_can_use_bibliography_year():
    message = message_from_archived_audit(
        complete_audit(year=""), complete_bibliography(year="2023")
    )
    assert year_value(message) == 2023


def test_year_value_uses_published_before_created():
    message = {
        "published": {"date-parts": [[2022, 7, 1]]},
        "created": {"date-time": "2021-12-30T00:00:00Z"},
    }
    assert year_value(message) == 2022


def test_year_value_falls_back_to_created_date_time():
    assert year_value({"created": {"date-time": "2020-03-02T08:00:00Z"}}) == 2020
