#!/usr/bin/env python3
"""Build a claim-level reference audit and Zotero-compatible exports."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


DOI_REFERENCES = [
    ("R01", "10.3390/s20247138", "Postural stability has been measured during virtual-reality exposure using an external balance reference.", ["postural stability", "virtual reality"]),
    ("R02", "10.1007/s10055-022-00637-3", "Consumer HMD tracking requires independent evaluation before metrological claims.", ["tracking", "accuracy"]),
    ("R03", "10.1007/s10055-022-00732-5", "Head orientation measured in HMD-based VR is behaviorally relevant but system dependent.", ["head orientation", "head-mounted"]),
    ("R04", "10.3390/s19143213", "Inertial HAR pipelines depend on acquisition, segmentation, features, and classification choices.", ["window", "feature"]),
    ("R05", "10.3390/s21196652", "Inertial sensing has been applied to distinguish behaviors performed while sitting.", ["sitting", "inertial"]),
    ("R06", "10.3390/s20030655", "Smartphone inertial streams can support activity analysis during seated media use.", ["sitting", "inertial"]),
    ("R07", "10.3390/s16040426", "Sensor placement and multi-sensor combinations affect activity-recognition results.", ["sensor", "placement"]),
    ("R08", "10.3390/s23249721", "A recent wearable-IMU HAR study used a deep convolutional pipeline with time-frequency features.", ["deep", "inertial"]),
    ("R09", "10.3390/s21227628", "A supervised IMU activity study separated model training from 10-fold cross-validation.", ["training", "cross-validation"]),
    ("R10", "10.3758/s13428-019-01242-0", "The Unity Experiment Framework is an open-source Unity resource for behavioral experiments that produces analysis-ready data files.", ["open-source resource", "data files"]),
    ("R11", "10.1186/s12984-022-01001-x", "OpenSense is an open-source IMU kinematics workflow that makes calibration, sensor fusion, and optical validation explicit.", ["open-source", "kinematics"]),
    ("R12", "10.3390/s18092892", "Windowed feature representation materially affects IMU activity classification.", ["window", "feature"]),
    ("R13", "10.3390/s18124189", "Different time- and frequency-domain feature sets can change HAR performance.", ["features", "classification"]),
    ("R14", "10.1162/imag.a.136", "Lab Streaming Layer synchronizes software streams using per-sample timestamps and network offset and jitter correction.", ["time stamps", "synchronizing"]),
    ("R15", "10.3390/s23010184", "IMU-HAR research includes sample-level data valuation within supervised model training.", ["data valuation", "training"]),
    ("R16", "10.3390/s20185264", "Data quality and reliability checks are necessary before downstream activity recognition.", ["data quality", "reliability"]),
    ("R17", "10.3390/s21082747", "IMU fusion algorithms differ in functional and implementation properties.", ["fusion", "algorithm"]),
    ("R18", "10.3390/s18114003", "Comparing IMU orientation with motion capture requires explicit frame alignment.", ["alignment", "motion capture"]),
    ("R19", "10.3390/s23146535", "Joint-angle derivation from IMUs depends on calibration, fusion, and anatomical alignment.", ["calibration", "joint angle"]),
    ("R20", "10.3390/mi13081283", "Low-cost attitude estimation depends on filtering and sensor-model assumptions.", ["attitude", "low-cost"]),
    ("R21", "10.3389/frobt.2021.772583", "Low-cost IMUs may require device-specific calibration.", ["calibration", "low-cost"]),
    ("R22", "10.3390/s24020686", "Low-cost IMU motion-capture workflows trade deployment simplicity against measurement constraints.", ["low-cost", "motion capture"]),
    ("R23", "10.3390/s23042342", "A low-cost flight-controller IMU was compared with commercial sensors for human-motion measurement.", ["compared", "commercial sensors"]),
    ("R24", "10.3390/s22051791", "Wearable IMU reporting is heterogeneous in devices, placement, and outcomes.", ["IMU", "review"]),
    ("R25", "10.1145/3641825.3689518", "Recent work directly compares inside-out tracking across Meta Quest 3, Pico 4 Pro, and other standalone HMDs.", ["tracking accuracy", "Pico 4 Pro"]),
    ("R26", "10.3390/s17061287", "Wearable-HAR acquisition is affected by sensor alignment, data loss, and noise.", ["alignment", "data losses"]),
    ("R27", "10.3390/s19030596", "Optical motion capture can serve as a reference for validating IMU-derived angles.", ["optical motion capture", "validation"]),
    ("R28", "10.3390/s22030956", "Drift and displacement estimation are central limitations in single-IMU motion analysis.", ["drift", "displacement"]),
    ("R29", "10.3390/s17071591", "Optical motion-capture systems have their own measurable positioning performance.", ["Vicon", "positioning"]),
]

WEB_REFERENCES = [
    ("R30", "W3C WebXR Device API", "https://www.w3.org/TR/webxr/", "WebXR exposes viewer and space poses through browser-managed XRFrame methods.", ["pose", "XRFrame"]),
    ("R31", "W3C Device Orientation and Motion", "https://www.w3.org/TR/orientation-event/", "The browser Device Motion API defines acceleration and rotation-rate event fields and an explicit permission procedure.", ["permission", "acceleration", "rotation rate"]),
    ("R32", "Android Sensors Overview", "https://developer.android.com/develop/sensors-and-location/sensors/sensors_overview", "The Android sensor framework distinguishes hardware-based and software-based sensors.", ["hardware-based", "software-based"]),
    ("R33", "Android Debug Bridge", "https://developer.android.com/tools/adb", "ADB is a command-line tool for communicating with an Android device.", ["command-line", "communicate"]),
    ("R34", "Khronos OpenXR Specification", "https://registry.khronos.org/OpenXR/specs/1.1/html/xrspec.html", "OpenXR locates a space pose at a specified historical or predicted time.", ["predicted", "pose"]),
]

WEB_EXCERPT_ANCHORS = {
    "R30": ["method provides the pose"],
    "R31": [
        "requires users to give express permission",
        "The acceleration attribute must return",
        "The rotationRate attribute must return",
    ],
    "R32": ["Some of these sensors are hardware-based"],
    "R33": ["Android Debug Bridge (adb) is a versatile command-line tool"],
    "R34": ["Applications use the xrLocateSpace function"],
}


class ContentBlockParser(HTMLParser):
    """Collect prose blocks while excluding page chrome and executable content."""

    BLOCK_TAGS = {"p", "dd"}
    EXCLUDED_TAGS = {"nav", "header", "footer", "script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.excluded_depth = 0
        self.block_depth = 0
        self.current: list[str] = []
        self.blocks: list[str] = []

    def flush_block(self) -> None:
        value = clean_text(" ".join(self.current))
        if value:
            self.blocks.append(value)
        self.current = []
        self.block_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in self.EXCLUDED_TAGS:
            self.excluded_depth += 1
            return
        if not self.excluded_depth and tag in self.BLOCK_TAGS:
            # W3C HTML commonly omits explicit </p> tags. A new prose block
            # therefore closes any active one before collection continues.
            if self.block_depth:
                self.flush_block()
            self.block_depth = 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.EXCLUDED_TAGS:
            self.excluded_depth = max(0, self.excluded_depth - 1)
            return
        if not self.excluded_depth and tag in self.BLOCK_TAGS and self.block_depth:
            self.flush_block()

    def handle_data(self, data: str) -> None:
        if not self.excluded_depth and self.block_depth:
            self.current.append(data)

    def close(self) -> None:
        super().close()
        if self.block_depth:
            self.flush_block()


def excerpt_has_all_keywords(excerpt: str, keywords: list[str]) -> bool:
    lowered = excerpt.lower()
    return bool(excerpt) and all(keyword.lower() in lowered for keyword in keywords)


def usable_web_block(value: str) -> bool:
    lowered = value.lower()
    return (
        len(value) >= 55
        and "table of contents" not in lowered
        and "github #" not in lowered
        and "idl index" not in lowered
        and "add a note about" not in lowered
        and not lowered.startswith("write and debug code")
        and not lowered.startswith("build projects")
    )


def usable_prior_web_excerpt(value: str, keywords: list[str]) -> bool:
    return usable_web_block(value) and excerpt_has_all_keywords(value, keywords)


def request_bytes(url: str, accept: str = "*/*", timeout: int = 8) -> tuple[int, str, bytes]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Pico4Pro-MotionExportAudit/1.0 (+https://github.com/U-uu-U/pico4-imu-data-quality)",
            "Accept": accept,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.geturl(), response.read()


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def first_value(message: dict, key: str, default=""):
    value = message.get(key, default)
    if isinstance(value, list):
        return value[0] if value else default
    return value


def author_text(message: dict) -> str:
    names = []
    for person in message.get("author", []):
        family = person.get("family", "")
        given = person.get("given", "")
        names.append(", ".join(part for part in (family, given) if part))
    return "; ".join(names)


def message_from_archived_audit(audit_row: dict, bibliography_row: dict) -> dict:
    """Reconstruct the Crossref fields already preserved by a prior verified run."""
    authors = []
    for name in audit_row.get("verified_authors", "").split("; "):
        if not name:
            continue
        family, _, given = name.partition(", ")
        authors.append({"family": family, "given": given})
    year = audit_row.get("verified_year", "") or bibliography_row.get("year", "")
    journal = audit_row.get("verified_journal", "") or bibliography_row.get(
        "journal_or_publisher", ""
    )
    return {
        "DOI": audit_row.get("doi", ""),
        "title": [audit_row.get("verified_title", "")],
        "container-title": [journal],
        "author": authors,
        "published": {"date-parts": [[int(year)]]} if str(year).isdigit() else {},
        "volume": bibliography_row.get("volume", ""),
        "issue": bibliography_row.get("issue", ""),
        "page": bibliography_row.get("pages_or_article", ""),
    }


def archived_crossref_metadata_complete(audit_row: dict, bibliography_row: dict) -> bool:
    """Return true only when archived metadata can recreate a complete citation."""
    year = audit_row.get("verified_year", "") or bibliography_row.get("year", "")
    journal = audit_row.get("verified_journal", "") or bibliography_row.get(
        "journal_or_publisher", ""
    )
    return bool(
        audit_row.get("crossref_status") == "PASS"
        and bibliography_row
        and clean_text(audit_row.get("verified_title", ""))
        and clean_text(audit_row.get("verified_authors", ""))
        and clean_text(journal)
        and str(year).isdigit()
    )


def year_value(message: dict, doi: str = "") -> int | str:
    journal = clean_text(first_value(message, "container-title")).lower()
    mdpi_sensors_match = re.fullmatch(r"10\.3390/s(\d{2})\d+", doi.lower())
    if journal == "sensors" and mdpi_sensors_match:
        # Crossref may expose the late-December online date even when the cited
        # Sensors volume and issue belong to the following publication year.
        return 2000 + int(mdpi_sensors_match.group(1))
    for field in ("published-print", "published-online", "published", "issued", "created"):
        date_record = message.get(field, {}) or {}
        parts = date_record.get("date-parts", [])
        if parts and parts[0]:
            return parts[0][0]
        date_time = str(date_record.get("date-time", ""))
        match = re.match(r"(\d{4})", date_time)
        if match:
            return int(match.group(1))
    return ""


def title_similarity(a: str, b: str) -> float:
    tokens_a = set(re.findall(r"[a-z0-9]+", a.lower()))
    tokens_b = set(re.findall(r"[a-z0-9]+", b.lower()))
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b) if tokens_a | tokens_b else 0.0


def crossref_message(doi: str, cache: dict) -> tuple[dict, str]:
    key = doi.lower()
    if key in cache:
        return cache[key], "local Crossref cache"
    status, _, payload = request_bytes(
        "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe=""),
        "application/json",
    )
    if status != 200:
        raise RuntimeError(f"Crossref returned {status} for {doi}")
    time.sleep(0.15)
    return json.loads(payload)["message"], "live Crossref API"


def europe_pmc_fulltext(doi: str, keywords: list[str]) -> tuple[str, str, str, str]:
    query = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=" + urllib.parse.quote(f"DOI:{doi}") + "&format=json"
    try:
        _, _, payload = request_bytes(query, "application/json")
        result = json.loads(payload).get("resultList", {}).get("result", [])
        pmcid = next((item.get("pmcid") for item in result if item.get("pmcid")), "")
        if not pmcid:
            return "not available", "", "", ""
        _, full_url, xml_bytes = request_bytes(
            f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML",
            "application/xml",
        )
        root = ET.fromstring(xml_bytes)
        parent = {child: node for node in root.iter() for child in node}
        candidates = []
        for element in root.findall(".//abstract//p") + root.findall(".//body//p"):
            text = clean_text(" ".join(element.itertext()))
            if not text:
                continue
            node = element
            section = "Abstract"
            while node in parent:
                node = parent[node]
                if node.tag.endswith("sec"):
                    title_node = node.find("title")
                    if title_node is not None:
                        section = clean_text(" ".join(title_node.itertext())) or section
                    break
            candidates.append((text, section))
        lowered_keywords = [k.lower() for k in keywords]
        matched = next(
            ((text, section) for text, section in candidates if all(k in text.lower() for k in lowered_keywords)),
            next(((text, section) for text, section in candidates if any(k in text.lower() for k in lowered_keywords)), ("", "")),
        )
        excerpt, section = matched
        return "Europe PMC full text", full_url, clean_text(excerpt)[:1600], f"{pmcid}, section: {section}"
    except Exception as exc:
        return f"full-text retrieval failed: {type(exc).__name__}", "", "", ""


def web_excerpt(
    url: str, keywords: list[str], anchors: list[str] | None = None
) -> tuple[int | str, str, str, str]:
    try:
        status, final_url, payload = request_bytes(url, "text/html,application/xhtml+xml")
        parser = ContentBlockParser()
        parser.feed(payload.decode("utf-8", errors="ignore"))
        parser.close()
        blocks = [block for block in parser.blocks if usable_web_block(block)]
        lowered_keywords = [keyword.lower() for keyword in keywords]

        if anchors:
            selected = []
            for anchor in anchors:
                candidates = [
                    block for block in blocks if anchor.lower() in block.lower()
                ]
                if not candidates:
                    selected = []
                    break
                selected.append(min(candidates, key=len))
            excerpt = " ".join(dict.fromkeys(selected))
            if excerpt_has_all_keywords(excerpt, keywords):
                return (
                    status,
                    final_url,
                    excerpt[:1600],
                    "web page, selected official definition paragraphs",
                )

        complete = [
            block
            for block in blocks
            if all(keyword in block.lower() for keyword in lowered_keywords)
        ]
        if complete:
            excerpt = min(complete, key=len)
            return status, final_url, excerpt[:1600], "web page, selected content paragraph"

        # Some specifications place permission and field semantics in separate
        # paragraphs. Combine the shortest prose block for each missing term.
        selected = []
        covered = set()
        for keyword in lowered_keywords:
            candidates = [
                block
                for block in blocks
                if keyword in block.lower() and block not in selected
            ]
            if candidates:
                block = min(candidates, key=len)
                selected.append(block)
                covered.update(
                    item for item in lowered_keywords if item in block.lower()
                )
        excerpt = " ".join(selected)
        if covered == set(lowered_keywords):
            return status, final_url, excerpt[:1600], "web page, selected content paragraphs"
        return status, final_url, "", "web page; no complete supporting prose located"
    except Exception as exc:
        return f"ERROR:{type(exc).__name__}", url, "", ""


def semantic_scholar_abstract(doi: str) -> tuple[str, str]:
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/DOI:" + urllib.parse.quote(doi, safe="/") + "?fields=abstract,url"
        _, _, payload = request_bytes(url, "application/json")
        message = json.loads(payload)
        return clean_text(message.get("abstract", "")), message.get("url", "")
    except Exception:
        return "", ""


def bibtex_entry(ref_id: str, message: dict, doi: str) -> str:
    title = clean_text(first_value(message, "title"))
    journal = clean_text(first_value(message, "container-title"))
    authors = " and ".join(
        "{family}, {given}".format(family=p.get("family", ""), given=p.get("given", ""))
        for p in message.get("author", [])
    )
    volume = message.get("volume", "")
    issue = message.get("issue", "")
    pages = message.get("page", message.get("article-number", ""))
    return (
        f"@article{{{ref_id},\n"
        f"  author = {{{authors}}},\n  title = {{{title}}},\n  journal = {{{journal}}},\n"
        f"  year = {{{year_value(message, doi)}}},\n  volume = {{{volume}}},\n  number = {{{issue}}},\n"
        f"  pages = {{{pages}}},\n  doi = {{{doi}}},\n  url = {{https://doi.org/{doi}}}\n}}\n"
    )


def ris_entry(message: dict, doi: str) -> str:
    lines = ["TY  - JOUR"]
    for person in message.get("author", []):
        lines.append(f"AU  - {person.get('family', '')}, {person.get('given', '')}".rstrip())
    lines.extend(
        [
            f"TI  - {clean_text(first_value(message, 'title'))}",
            f"JO  - {clean_text(first_value(message, 'container-title'))}",
            f"PY  - {year_value(message, doi)}",
            f"VL  - {message.get('volume', '')}",
            f"IS  - {message.get('issue', '')}",
            f"SP  - {message.get('page', message.get('article-number', ''))}",
            f"DO  - {doi}",
            f"UR  - https://doi.org/{doi}",
            "ER  -",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--crossref-cache", type=Path)
    args = parser.parse_args()
    evidence = args.output_root / "evidence"
    references = args.output_root / "references"
    references.mkdir(parents=True, exist_ok=True)
    cache = {}
    if args.crossref_cache and args.crossref_cache.exists():
        cache = json.loads(args.crossref_cache.read_text(encoding="utf-8-sig"))

    prior_by_doi = {}
    prior_by_url = {}
    prior_audit = evidence / "reference_claim_audit.csv"
    if prior_audit.exists():
        with prior_audit.open("r", encoding="utf-8-sig", newline="") as f:
            prior_rows = list(csv.DictReader(f))
            prior_by_doi = {row["doi"].lower(): row for row in prior_rows if row.get("doi")}
            prior_by_url = {row["url"]: row for row in prior_rows if row.get("url")}
    prior_bibliography_by_doi = {}
    prior_bibliography = references / "bibliography_verified.csv"
    if prior_bibliography.exists():
        with prior_bibliography.open("r", encoding="utf-8-sig", newline="") as f:
            prior_bibliography_by_doi = {
                row["doi_or_url"].lower(): row
                for row in csv.DictReader(f)
                if row.get("type") == "journal" and row.get("doi_or_url")
            }

    audit = []
    bibliography = []
    bib_entries = []
    ris_entries = []
    for ref_id, doi, claim, keywords in DOI_REFERENCES:
        prior = prior_by_doi.get(doi.lower(), {})
        prior_bib = prior_bibliography_by_doi.get(doi.lower(), {})
        if archived_crossref_metadata_complete(prior, prior_bib):
            message = message_from_archived_audit(prior, prior_bib)
            crossref_source = "archived previously verified Crossref metadata"
        else:
            message, crossref_source = crossref_message(doi, cache)
        title = clean_text(first_value(message, "title"))
        if prior:
            landing_status = prior.get("doi_landing_status", "")
            landing_url = prior.get("doi_landing_url", f"https://doi.org/{doi}")
        else:
            try:
                landing_status, landing_url, _ = request_bytes(f"https://doi.org/{doi}", "text/html")
            except urllib.error.HTTPError as exc:
                landing_status, landing_url = exc.code, exc.geturl()
            except Exception as exc:
                landing_status, landing_url = f"ERROR:{type(exc).__name__}", f"https://doi.org/{doi}"
        if prior.get("verbatim_supporting_excerpt"):
            fulltext_level = prior.get("claim_evidence_level", "prior verified evidence")
            fulltext_url = prior.get("claim_evidence_url", "")
            excerpt = prior["verbatim_supporting_excerpt"]
            locator = prior.get("claim_evidence_locator", "")
        else:
            excerpt = clean_text(message.get("abstract", ""))[:900]
            if excerpt:
                fulltext_level = "Crossref abstract fallback"
                fulltext_url = f"https://api.crossref.org/works/{doi}"
                locator = "Crossref abstract"
        if not excerpt:
            excerpt, fulltext_url = semantic_scholar_abstract(doi)
            excerpt = excerpt[:1600]
            if excerpt:
                fulltext_level = "Semantic Scholar abstract fallback"
                locator = "Semantic Scholar abstract; publisher full text is closed"
        current_hits = [keyword for keyword in keywords if keyword.lower() in excerpt.lower()]
        if not excerpt or not current_hits:
            pmc_level, pmc_url, pmc_excerpt, pmc_locator = europe_pmc_fulltext(doi, keywords)
            pmc_hits = [keyword for keyword in keywords if keyword.lower() in pmc_excerpt.lower()]
            if pmc_excerpt and pmc_hits:
                fulltext_level, fulltext_url, excerpt, locator = (
                    pmc_level,
                    pmc_url,
                    pmc_excerpt,
                    pmc_locator,
                )
        metadata_passed = bool(title and message.get("DOI", "").lower() == doi.lower())
        excerpt_keywords = [keyword for keyword in keywords if keyword.lower() in excerpt.lower()]
        landing_resolved = str(landing_status).startswith(("2", "3"))
        record_complete = bool(metadata_passed and landing_resolved and excerpt and excerpt_keywords)
        audit.append(
            {
                "reference_id": ref_id,
                "intended_claim": claim,
                "doi": doi,
                "url": f"https://doi.org/{doi}",
                "crossref_status": "PASS" if message.get("DOI", "").lower() == doi.lower() else "FAIL",
                "crossref_source": crossref_source,
                "verified_title": title,
                "verified_authors": author_text(message),
                "verified_year": year_value(message, doi),
                "verified_journal": clean_text(first_value(message, "container-title")),
                "doi_landing_status": landing_status,
                "doi_landing_url": landing_url,
                "claim_evidence_level": fulltext_level,
                "claim_evidence_url": fulltext_url,
                "claim_evidence_locator": locator,
                "verbatim_supporting_excerpt": excerpt,
                "claim_keyword_hits": "|".join(excerpt_keywords),
                "semantic_scope_note": "Excerpt located by keywords; author must confirm that the cited passage supports the final manuscript wording.",
                "semantic_review_status": "PENDING_AUTHOR_REVIEW",
                "audit_status": "AUTOMATED_RECORD_COMPLETE" if record_complete else "MANUAL_RECORD_CHECK",
            }
        )
        bibliography.append(
            {
                "reference_id": ref_id,
                "type": "journal",
                "authors": author_text(message),
                "title": title,
                "journal_or_publisher": clean_text(first_value(message, "container-title")),
                "year": year_value(message, doi),
                "volume": message.get("volume", ""),
                "issue": message.get("issue", ""),
                "pages_or_article": message.get("page", message.get("article-number", "")),
                "doi_or_url": doi,
            }
        )
        bib_entries.append(bibtex_entry(ref_id, message, doi))
        ris_entries.append(ris_entry(message, doi))
        print(f"reference {ref_id}: {doi} -> {'record complete' if record_complete else 'manual record check'}", flush=True)
        time.sleep(0.1)

    for ref_id, title, url, claim, keywords in WEB_REFERENCES:
        prior = prior_by_url.get(url, {})
        prior_excerpt = prior.get("verbatim_supporting_excerpt", "")
        if usable_prior_web_excerpt(prior_excerpt, keywords):
            status = prior.get("doi_landing_status", "previously resolved")
            final_url = prior.get("doi_landing_url", url)
            excerpt = prior_excerpt
            locator = prior.get("claim_evidence_locator", "archived web excerpt")
        else:
            status, final_url, excerpt, locator = web_excerpt(
                url, keywords, WEB_EXCERPT_ANCHORS.get(ref_id)
            )
        passed = bool(
            excerpt_has_all_keywords(excerpt, keywords)
            and str(status).startswith(("2", "3"))
        )
        audit.append(
            {
                "reference_id": ref_id,
                "intended_claim": claim,
                "doi": "",
                "url": url,
                "crossref_status": "NOT_APPLICABLE",
                "crossref_source": "standards/developer documentation",
                "verified_title": title,
                "verified_authors": "",
                "verified_year": "",
                "verified_journal": "",
                "doi_landing_status": status,
                "doi_landing_url": final_url,
                "claim_evidence_level": "authoritative web specification/documentation",
                "claim_evidence_url": final_url,
                "claim_evidence_locator": locator,
                "verbatim_supporting_excerpt": excerpt,
                "claim_keyword_hits": "|".join(
                    keyword for keyword in keywords if keyword.lower() in excerpt.lower()
                ),
                "semantic_scope_note": "Excerpt located by keywords; author must confirm that the cited passage supports the final manuscript wording.",
                "semantic_review_status": "PENDING_AUTHOR_REVIEW",
                "audit_status": "AUTOMATED_RECORD_COMPLETE" if passed else "MANUAL_RECORD_CHECK",
            }
        )
        bibliography.append(
            {
                "reference_id": ref_id,
                "type": "web",
                "authors": "",
                "title": title,
                "journal_or_publisher": title.split()[0],
                "year": "",
                "volume": "",
                "issue": "",
                "pages_or_article": "",
                "doi_or_url": url,
            }
        )
        print(f"reference {ref_id}: {url} -> {'record complete' if passed else 'manual record check'}", flush=True)

    missing_doi_years = [
        row["reference_id"]
        for row in bibliography
        if row["type"] == "journal" and not str(row["year"]).strip()
    ]
    if missing_doi_years:
        raise RuntimeError(
            "DOI bibliography records without a publication year: "
            + ", ".join(missing_doi_years)
        )

    fields = list(audit[0])
    with (evidence / "reference_claim_audit.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(audit)
    fields = list(bibliography[0])
    with (references / "bibliography_verified.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(bibliography)
    (references / "sensors_motion_export_audit.bib").write_text("\n".join(bib_entries), encoding="utf-8")
    (references / "sensors_motion_export_audit.ris").write_text("\n".join(ris_entries), encoding="utf-8")
    summary = {
        "reference_count": len(audit),
        "crossref_verified_doi_count": sum(r["crossref_status"] == "PASS" for r in audit),
        "doi_records_with_publication_year": sum(
            row["type"] == "journal" and bool(str(row["year"]).strip())
            for row in bibliography
        ),
        "authoritative_web_count": len(WEB_REFERENCES),
        "full_text_count": sum(r["claim_evidence_level"] == "Europe PMC full text" for r in audit),
        "abstract_fallback_count": sum("abstract fallback" in r["claim_evidence_level"] for r in audit),
        "automated_record_complete_count": sum(
            r["audit_status"] == "AUTOMATED_RECORD_COMPLETE" for r in audit
        ),
        "manual_record_check_count": sum(
            r["audit_status"] != "AUTOMATED_RECORD_COMPLETE" for r in audit
        ),
        "pending_author_semantic_review_count": sum(
            r["semantic_review_status"] == "PENDING_AUTHOR_REVIEW" for r in audit
        ),
    }
    (references / "reference_audit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
