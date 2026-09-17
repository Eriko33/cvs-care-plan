"""Parse an SPL label XML into RAG-ready chunks.

Chunking strategy:
- First split by <section> (each section already has a LOINC code + a single topic).
- Within a section, tables are always kept as ONE chunk (row/column integrity matters
  more than chunk-size consistency for dosing tables).
- Free-text parts (paragraphs/lists) longer than CHUNK_SIZE_WORDS are further split
  with a sliding window and overlap, so a fact near a cut point isn't stranded.
- Every chunk is prefixed with "[<drug> — <section name>]" so it still makes sense
  when retrieved on its own, out of context.

Usage:
    python -m rag.chunk_label labels/privigen.xml "Privigen"
"""
import sys
from dataclasses import dataclass

from lxml import etree

NS = {"v3": "urn:hl7-org:v3"}

# LOINC section code -> human-readable name (extend as you encounter more).
SECTION_NAMES = {
    "34067-9": "Indications and Usage",
    "34068-7": "Dosage and Administration",
    "34069-5": "Dosage Forms and Strengths",
    "34070-3": "Contraindications",
    "34071-1": "Warnings and Precautions",
    "34084-4": "Adverse Reactions",
    "34073-7": "Drug Interactions",
    "34080-2": "Use in Specific Populations",
    "34090-1": "Clinical Pharmacology",
    "34091-9": "How Supplied/Storage and Handling",
    "42232-9": "Precautions",
    "43685-7": "Warnings",
}

CHUNK_SIZE_WORDS = 350   # roughly 450-500 tokens of English clinical text
CHUNK_OVERLAP_WORDS = 60  # ~15-20% overlap between adjacent chunks

# Carton/vial artwork text, not clinical content — pure noise for RAG.
# Add more codes here if a label surfaces other package-label sections.
NOISE_SECTION_CODES = {
    "51945-4",  # PACKAGE LABEL.PRINCIPAL DISPLAY PANEL
}


@dataclass
class Chunk:
    drug_name: str
    section_name: str
    loinc_code: str | None
    chunk_index: int
    text: str


def clean_text(elem) -> str:
    return " ".join("".join(elem.itertext()).split())


def extract_table(table_elem) -> str:
    rows = []
    for tr in table_elem.findall(".//v3:tr", NS):
        cells = [clean_text(td) for td in (tr.findall("./v3:td", NS) or tr.findall("./v3:th", NS))]
        if cells:
            rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def extract_sections(xml_path: str) -> list[dict]:
    tree = etree.parse(xml_path)
    root = tree.getroot()
    sections = []

    for section in root.findall(".//v3:section", NS):
        code_elem = section.find("./v3:code", NS)
        loinc_code = code_elem.get("code") if code_elem is not None else None
        if loinc_code in NOISE_SECTION_CODES:
            continue

        # Real SPL files use plenty of subsections with a generic
        # "SPL UNCLASSIFIED SECTION" code (e.g. per-indication dosing
        # subsections) — their own <title> is the only meaningful name,
        # so it takes priority over the LOINC lookup table.
        title_elem = section.find("./v3:title", NS)
        title = clean_text(title_elem) if title_elem is not None else None
        display_name = code_elem.get("displayName") if code_elem is not None else None
        section_name = title or SECTION_NAMES.get(loinc_code) or display_name or loinc_code or "Unknown Section"

        parts = []
        text_elem = section.find("./v3:text", NS)
        if text_elem is not None:
            for child in text_elem:
                tag = etree.QName(child).localname
                if tag == "paragraph":
                    text = clean_text(child)
                    if text:
                        parts.append(("text", text))
                elif tag == "list":
                    items = [f"- {clean_text(item)}" for item in child.findall("./v3:item", NS) if clean_text(item)]
                    if items:
                        parts.append(("text", "\n".join(items)))
                elif tag == "table":
                    table_text = extract_table(child)
                    if table_text:
                        parts.append(("table", table_text))
                # anything else (renderMultiMedia, footnote, etc.) is intentionally skipped

        if parts:
            sections.append({"loinc_code": loinc_code, "section_name": section_name, "parts": parts})

    return sections


def split_text_with_overlap(text: str, size: int = CHUNK_SIZE_WORDS, overlap: int = CHUNK_OVERLAP_WORDS) -> list[str]:
    words = text.split()
    if len(words) <= size:
        return [text]

    pieces = []
    start = 0
    while start < len(words):
        end = start + size
        pieces.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap
    return pieces


def chunk_label(xml_path: str, drug_name: str) -> list[Chunk]:
    chunks = []
    for section in extract_sections(xml_path):
        idx = 0
        for part_type, part_text in section["parts"]:
            # Tables are never split further, regardless of size.
            pieces = [part_text] if part_type == "table" else split_text_with_overlap(part_text)
            for piece in pieces:
                header = f"[{drug_name} — {section['section_name']}]"
                chunks.append(
                    Chunk(
                        drug_name=drug_name,
                        section_name=section["section_name"],
                        loinc_code=section["loinc_code"],
                        chunk_index=idx,
                        text=f"{header}\n{piece}",
                    )
                )
                idx += 1
    return chunks


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    xml_path, drug_name = sys.argv[1], sys.argv[2]
    result = chunk_label(xml_path, drug_name)
    print(f"{len(result)} chunks extracted from {xml_path}\n")
    for c in result:
        word_count = len(c.text.split())
        print(f"--- {c.section_name} [chunk {c.chunk_index}] ({word_count} words) ---")
        print(c.text[:200].replace("\n", " ") + ("..." if len(c.text) > 200 else ""))
        print()
