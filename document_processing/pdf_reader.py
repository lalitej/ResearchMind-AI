
import fitz
import re
import time
from pathlib import Path
from typing import Union, BinaryIO


# =========================================
# TEXT CLEANING
# =========================================

def clean_page_text(text: str) -> str:

    if not text:
        return ""

    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# =========================================
# METADATA
# =========================================

def extract_title_from_first_page(page):
    """Recover a missing PDF title from prominent first-page typography."""
    try:
        page_dict = page.get_text("dict")
        page_height = float(page.rect.height)
    except Exception:
        return "Unknown title"

    spans = []
    all_sizes = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                value = " ".join(str(span.get("text", "")).split()).strip()
                if not value:
                    continue
                try:
                    size = float(span.get("size", 0))
                    bbox = span.get("bbox", (0, 0, 0, 0))
                    y0, x0 = float(bbox[1]), float(bbox[0])
                except (TypeError, ValueError, IndexError):
                    continue
                all_sizes.append(size)
                spans.append({"text": value, "size": size, "y": y0, "x": x0})

    if not spans or not all_sizes:
        return "Unknown title"

    median_size = sorted(all_sizes)[len(all_sizes) // 2]
    minimum_size = max(12.0, median_size * 1.2)
    excluded = re.compile(r"(arxiv:|doi:|https?://|www\.|copyright|permission|received|accepted|published|preprint)", re.I)
    candidates = [item for item in spans
                  if item["size"] >= minimum_size
                  and item["y"] <= page_height * 0.55
                  and not excluded.search(item["text"])]
    if not candidates:
        return "Unknown title"

    candidates.sort(key=lambda item: (item["y"], item["x"]))
    groups = []
    for item in candidates:
        if not groups:
            groups.append([item])
            continue
        previous = groups[-1][-1]
        gap = item["y"] - previous["y"]
        max_gap = max(10.0, min(item["size"], previous["size"]) * 1.8)
        similar_size = abs(item["size"] - previous["size"]) <= 2.5
        if -2.0 <= gap <= max_gap and similar_size:
            groups[-1].append(item)
        else:
            groups.append([item])

    ranked = []
    for group in groups:
        text = " ".join(item["text"] for item in group).strip()
        text = re.sub(r"\s+", " ", text)
        if len(text) < 5 or len(text) > 300:
            continue
        if excluded.search(text):
            continue
        average_size = sum(item["size"] for item in group) / len(group)
        top_position = min(item["y"] for item in group)
        # Prefer large, title-like multiword text near the top, not short labels.
        score = average_size * 3 + min(len(text.split()), 18) * 0.8 - top_position / max(page_height, 1) * 4
        if len(text.split()) >= 3:
            score += 2
        ranked.append((score, text))

    if not ranked:
        return "Unknown title"
    ranked.sort(reverse=True)
    return ranked[0][1]


def extract_metadata(document, first_page=None):

    metadata = document.metadata or {}
    title = metadata.get("title") or ""
    if not title and first_page is not None:
        title = extract_title_from_first_page(first_page)

    return {
        "title": title or "Unknown title",
        "author": metadata.get("author") or "Unknown author",
        "subject": metadata.get("subject") or "",
        "keywords": metadata.get("keywords") or "",
        "creator": metadata.get("creator") or "",
        "page_count": len(document)
    }


# =========================================
# OPTIONAL TABLE EXTRACTION
# =========================================

def extract_page_tables(page):

    tables = []

    if not hasattr(page, "find_tables"):
        return tables

    try:

        table_finder = page.find_tables()

        for index, table in enumerate(
            table_finder.tables,
            start=1
        ):

            extracted_data = table.extract()

            if extracted_data:

                tables.append({
                    "table_number": index,
                    "rows": extracted_data
                })

    except Exception:
        pass

    return tables


# =========================================
# COORDINATE-BASED TABLE HEADER DETECTION
# =========================================

# =========================================
# COORDINATE-BASED TABLE EXTRACTION
# =========================================

def extract_coordinate_tables(page, page_text=None):

    tables = []

    # The coordinate reconstruction below is intended for a narrow family of
    # benchmark tables. Most article pages cannot contain a matching header.
    # Pre-filter using already-extracted text to avoid a second PyMuPDF word pass.
    if page_text is not None:
        page_tokens = set(re.findall(r"[a-z]+", page_text.lower()))
        if not (page_tokens.intersection({"system", "systems", "model", "models"})
                and "dev" in page_tokens and "test" in page_tokens):
            return tables

    try:

        words = page.get_text("words")

        if not words:
            return tables

        # -------------------------------------
        # GROUP WORDS BY APPROXIMATE BASELINE
        # -------------------------------------

        rows = {}

        for word in words:

            x0, y0, x1, y1, text = word[:5]

            key = round(y0 / 2.5)

            rows.setdefault(key, []).append({
                "text": text.strip(),
                "x0": float(x0),
                "x1": float(x1),
                "y0": float(y0),
                "y1": float(y1)
            })

        sorted_rows = sorted(
            rows.values(),
            key=lambda row: min(item["y0"] for item in row)
        )

        # -------------------------------------
        # DETECT TABLE HEADERS
        # -------------------------------------

        for row in sorted_rows:

            row.sort(key=lambda item: item["x0"])

            for index, item in enumerate(row):

                if item["text"].lower() not in {
                    "system", "systems", "model", "models"
                }:
                    continue

                following = row[index + 1:]

                dev = next(
                    (
                        candidate for candidate in following
                        if candidate["text"].lower() == "dev"
                    ),
                    None
                )

                test = next(
                    (
                        candidate for candidate in following
                        if candidate["text"].lower() == "test"
                        and dev is not None
                        and candidate["x0"] > dev["x0"]
                    ),
                    None
                )

                if dev is None or test is None:
                    continue

                header = [item, dev, test]

                # ---------------------------------
                # DETECT SECONDARY METRIC HEADERS
                # ---------------------------------

                secondary_header = []

                metric_names = {
                    "em", "f1", "accuracy",
                    "precision", "recall",
                    "bleu", "rouge"
                }

                test_index = row.index(test)

                for candidate in row[index + 1:test_index + 2]:

                    if candidate["text"].lower() in metric_names:
                        secondary_header.append(candidate)

                if not secondary_header:

                    for candidate in words:

                        x0, y0, x1, y1, text = candidate[:5]

                        if (
                            abs(y0 - (item["y0"] + 10)) <= 2.5
                            and text.lower() in metric_names
                            and item["x0"] < x0 < test["x0"] + 25
                        ):

                            secondary_header.append({
                                "text": text.strip(),
                                "x0": float(x0),
                                "x1": float(x1),
                                "y0": float(y0),
                                "y1": float(y1)
                            })

                secondary_header.sort(
                    key=lambda value: value["x0"]
                )

                # ---------------------------------
                # DETERMINE NUMERIC COLUMN CENTERS
                # ---------------------------------

                metric_columns = (
                    secondary_header
                    if secondary_header
                    else [dev, test]
                )

                metric_centers = [
                    (value["x0"] + value["x1"]) / 2
                    for value in metric_columns
                ]

                # ---------------------------------
                # LIMIT TABLE HORIZONTAL REGION
                # ---------------------------------

                page_midpoint = page.rect.width / 2

                if item["x0"] > page_midpoint:

                    left_bound = item["x0"] - 20

                else:

                    left_bound = item["x0"] - 60

                right_bound = metric_centers[-1] + 20

                # ---------------------------------
                # FIND AND PRESERVE THE NEXT TABLE CAPTION
                # Restrict matching to the same horizontal table region.

                caption_positions = []

                # Captions can begin slightly left of the table body,
                # especially in two-column research papers.

                caption_left_bound = max(0, left_bound - 70)

                for word in words:

                    x0, y0, x1, y1, text = word[:5]

                    if (
                        text.lower().startswith("table")
                        and y0 > item["y0"] + 15
                        and caption_left_bound <= x0 <= right_bound
                    ):

                        caption_positions.append(float(y0))

                caption_y = (
                    min(caption_positions)
                    if caption_positions
                    else None
                )

                end_y = (
                    caption_y
                    if caption_y is not None
                    else item["y0"] + 180
                )

                # Capture the caption and its wrapped continuation lines.

                caption_text = ""

                if caption_y is not None:

                    caption_line_groups = {}

                    for word in words:

                        x0, y0, x1, y1, text = word[:5]

                        if (
                            caption_left_bound <= x0 <= right_bound
                            and caption_y - 1 <= y0 <= caption_y + 38
                        ):

                            line_key = round(y0 / 2.5)

                            caption_line_groups.setdefault(
                                line_key, []
                            ).append({
                                "text": text.strip(),
                                "x0": float(x0)
                            })

                    caption_lines = []

                    # Sort caption lines from top to bottom.
                    for _, line_words in sorted(
                        caption_line_groups.items()
                    ):

                        line_words.sort(
                            key=lambda value: value["x0"]
                        )

                        line_text = " ".join(
                            value["text"] for value in line_words
                        ).strip()

                        if line_text:
                            caption_lines.append(line_text)

                    caption_text = " ".join(caption_lines).strip()

                # COLLECT BODY WORDS
                # ---------------------------------

                body_words = []

                for word in words:

                    x0, y0, x1, y1, text = word[:5]

                    if (
                        left_bound <= x0 <= right_bound
                        and item["y0"] + 8 < y0 < end_y
                    ):

                        body_words.append({
                            "text": text.strip(),
                            "x0": float(x0),
                            "x1": float(x1),
                            "y0": float(y0),
                            "y1": float(y1)
                        })

                body_words.sort(
                    key=lambda value: value["y0"]
                )

                # ---------------------------------
                # GROUP WORDS USING VERTICAL OVERLAP
                # ---------------------------------

                body_rows = []

                for word in body_words:

                    matching_row = None

                    for existing_row in body_rows:

                        row_top = min(
                            value["y0"]
                            for value in existing_row
                        )

                        row_bottom = max(
                            value["y1"]
                            for value in existing_row
                        )

                        overlap = min(
                            row_bottom,
                            word["y1"]
                        ) - max(
                            row_top,
                            word["y0"]
                        )

                        if overlap > 0:

                            matching_row = existing_row
                            break

                    if matching_row is None:

                        body_rows.append([word])

                    else:

                        matching_row.append(word)

                # ---------------------------------
                # RECONSTRUCT TABLE CELLS
                # ---------------------------------

                extracted_rows = []

                for body_row in body_rows:

                    body_row.sort(
                        key=lambda value: value["x0"]
                    )

                    model_words = []

                    metric_values = [
                        []
                        for _ in metric_centers
                    ]

                    for word in body_row:

                        center = (
                            word["x0"] + word["x1"]
                        ) / 2

                        # Assign numbers and dashes
                        # to the nearest metric column.

                        nearest_index = min(
                            range(len(metric_centers)),
                            key=lambda i: abs(
                                center - metric_centers[i]
                            )
                        )

                        distance = abs(
                            center - metric_centers[nearest_index]
                        )

                        is_value = (
                            word["text"] == "-"
                            or re.fullmatch(
                                r"\d+(?:\.\d+)?",
                                word["text"]
                            ) is not None
                        )

                        if (
                            is_value
                            and distance <= 13
                        ):

                            metric_values[nearest_index].append(
                                word["text"]
                            )

                        elif center < metric_centers[0] - 10:

                            model_words.append(word["text"])

                    model_name = " ".join(
                        model_words
                    ).strip()

                    values = [
    (
        "Not reported"
        if not value or all(item == "-" for item in value)
        else " ".join(value).strip()
    )
    for value in metric_values
]

                    if not model_name:
                        continue

                    # ---------------------------------
                    # PRESERVE SECTION LABELS
                    # ---------------------------------

                    if model_name.lower() in {
                        "published", "ours"
                    }:

                        extracted_rows.append({
                            "type": "section",
                            "name": model_name
                        })

                        continue

                    # ---------------------------------
                    # SKIP NON-DATA PARAGRAPH HEADINGS
                    # ---------------------------------

                    if not any(
                        value != "Not reported"
                        for value in values
                    ):

                        continue

                    extracted_rows.append({
                        "type": "data",
                        "model": model_name,
                        "values": values
                    })

                # ---------------------------------
                # SAVE TABLE
                # ---------------------------------

                tables.append({

                    "header_y": item["y0"],

                    "caption": caption_text,

                    "caption_y": caption_y,

                    "header": [
                        {
                            "text": value["text"],
                            "x0": value["x0"],
                            "x1": value["x1"]
                        }
                        for value in header
                    ],

                    "secondary_header": [
                        {
                            "text": value["text"],
                            "x0": value["x0"],
                            "x1": value["x1"]
                        }
                        for value in secondary_header
                    ],

                    "metric_columns": [
                        {
                            "name": value["text"],
                            "center": center
                        }
                        for value, center in zip(
                            metric_columns,
                            metric_centers
                        )
                    ],

                    "rows": extracted_rows

                })

        return tables

    except Exception as exc:

        print(
            f"Coordinate table extraction warning: {exc}"
        )

        return tables

# =========================================
# PROCESS ONE PAGE
# =========================================

def process_page(
    page,
    page_number,
    extract_tables=False
):

    # Extract text without the extra sorting pass.
    raw_text = page.get_text("text")

    cleaned_text = clean_page_text(raw_text)

    word_count = len(cleaned_text.split())

    tables = (
        extract_page_tables(page)
        if extract_tables
        else []
    )
    coordinate_tables = extract_coordinate_tables(
        page, page_text=cleaned_text
    )

    return {
    "page_number": page_number,
    "text": cleaned_text,
    "word_count": word_count,
    "character_count": len(cleaned_text),
    "needs_ocr": len(cleaned_text) < 40,
    "tables": tables,
    "coordinate_tables": coordinate_tables
}


# =========================================
# MAIN PDF EXTRACTION
# =========================================

def extract_pdf(
    pdf_source: Union[str, Path, bytes, bytearray, BinaryIO],
    extract_tables=False
):

    start_time = time.perf_counter()

    document = None

    try:

        # -------------------------------------
        # OPEN PDF
        # -------------------------------------

        if isinstance(pdf_source, (str, Path)):

            document = fitz.open(str(pdf_source))

        elif isinstance(pdf_source, (bytes, bytearray)):

            document = fitz.open(
                stream=pdf_source,
                filetype="pdf"
            )

        elif hasattr(pdf_source, "read"):

            pdf_bytes = pdf_source.read()

            if hasattr(pdf_source, "seek"):
                pdf_source.seek(0)

            document = fitz.open(
                stream=pdf_bytes,
                filetype="pdf"
            )

        else:

            raise ValueError(
                "Unsupported PDF input type."
            )

        # -------------------------------------
        # VALIDATE PDF
        # -------------------------------------

        if document.is_encrypted:

            raise ValueError(
                "This PDF is password protected."
            )

        if len(document) == 0:

            raise ValueError(
                "The uploaded PDF contains no pages."
            )

        # -------------------------------------
        # EXTRACT METADATA
        # -------------------------------------

        metadata = extract_metadata(document, document[0])

        # -------------------------------------
        # FAST PAGE EXTRACTION
        # -------------------------------------

        pages = []

        for index in range(len(document)):

            page = document.load_page(index)

            page_data = process_page(
                page,
                page_number=index + 1,
                extract_tables=extract_tables
            )

            pages.append(page_data)

        # -------------------------------------
        # COMBINE TEXT
        # -------------------------------------

        full_text = "\n\n".join(
            f"[PAGE {page['page_number']}]\n{page['text']}"
            for page in pages
            if page["text"]
        )

        total_words = sum(
            page["word_count"]
            for page in pages
        )

        scanned_pages = [
            page["page_number"]
            for page in pages
            if page["needs_ocr"]
        ]

        # -------------------------------------
        # WARNINGS
        # -------------------------------------

        warnings = []

        if not full_text.strip():

            warnings.append(
                "No readable text was extracted. "
                "This document may require OCR."
            )

        if scanned_pages:

            warnings.append(
                f"{len(scanned_pages)} page(s) may require OCR."
            )

        if total_words < 100 and len(document) > 1:

            warnings.append(
                "Very little text was extracted. "
                "Please verify document readability."
            )

        # -------------------------------------
        # RESULT
        # -------------------------------------

        extraction_time = round(
            time.perf_counter() - start_time,
            3
        )
        print(
            f"ResearchMind: PDF extraction completed in {extraction_time:.3f}s "
            f"({len(document)} pages, {total_words:,} words)."
        )

        return {
            "success": bool(full_text.strip()),
            "metadata": metadata,
            "pages": pages,
            "full_text": full_text,
            "total_pages": len(document),
            "total_words": total_words,
            "scanned_pages": scanned_pages,
            "needs_ocr": bool(scanned_pages),
            "warnings": warnings,
            "extraction_time": extraction_time
        }

    except ValueError:
        raise

    except Exception as error:

        raise ValueError(
            f"PDF processing failed: {str(error)}"
        ) from error

    finally:

        if document is not None:
            document.close()
