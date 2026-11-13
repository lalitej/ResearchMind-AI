
import ipaddress
import socket
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from document_processing.pdf_reader import extract_pdf


# =========================================
# CONFIGURATION
# =========================================

REQUEST_TIMEOUT = (10, 25)
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 5
MIN_ARTICLE_WORDS = 100

HEADERS = {
    "User-Agent": (
        "ResearchMindAI/3.0 "
        "(Academic Research Analyzer)"
    )
}


# =========================================
# URL VALIDATION
# =========================================

def validate_url(url):

    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                "Only HTTP and HTTPS URLs are supported."
            )

        if not parsed.hostname:
            raise ValueError(
                "Invalid URL. Enter a complete URL."
            )

        if parsed.username or parsed.password:
            raise ValueError(
                "URLs containing login credentials "
                "are not supported."
            )

        # Validate port syntax.
        _ = parsed.port

        hostname = parsed.hostname.lower()

        if (
            hostname == "localhost"
            or hostname.endswith(".localhost")
        ):
            raise ValueError(
                "Localhost URLs are not supported."
            )

        # Resolve hostname.
        addresses = socket.getaddrinfo(
            hostname,
            parsed.port or (
                443 if parsed.scheme == "https" else 80
            ),
            type=socket.SOCK_STREAM
        )

        if not addresses:
            raise ValueError(
                "Unable to resolve the website address."
            )

        for address in addresses:

            ip = ipaddress.ip_address(
                address[4][0]
            )

            if not ip.is_global:
                raise ValueError(
                    "Private or local network URLs "
                    "are not allowed."
                )

        return url

    except ValueError:
        raise

    except socket.gaierror as error:
        raise ValueError(
            "Unable to resolve the website address."
        ) from error

    except Exception as error:
        raise ValueError(
            f"Invalid URL: {error}"
        ) from error


# =========================================
# DOWNLOAD WEB CONTENT
# =========================================

def download_url(url):

    current_url = url

    session = requests.Session()

    try:

        for _ in range(MAX_REDIRECTS + 1):

            # Validate every redirect destination.
            validate_url(current_url)

            try:

                response = session.get(
                    current_url,
                    headers=HEADERS,
                    timeout=REQUEST_TIMEOUT,
                    stream=True,
                    allow_redirects=False
                )

            except requests.RequestException as error:

                raise ValueError(
                    f"Unable to access the research paper: {error}"
                ) from error

            # Handle redirects.
            if response.status_code in (
                301, 302, 303, 307, 308
            ):

                location = response.headers.get(
                    "Location"
                )

                response.close()

                if not location:
                    raise ValueError(
                        "Website returned an invalid redirect."
                    )

                current_url = urljoin(
                    current_url,
                    location
                )

                continue

            try:

                response.raise_for_status()

                # Check file size before downloading.
                content_length = response.headers.get(
                    "Content-Length"
                )

                if content_length:

                    try:
                        content_length = int(content_length)
                    except ValueError:
                        content_length = None

                    if (
                        content_length is not None
                        and content_length > MAX_DOWNLOAD_BYTES
                    ):
                        raise ValueError(
                            "File is too large. "
                            "Maximum download size is 20 MB."
                        )

                content = bytearray()

                for chunk in response.iter_content(
                    chunk_size=65536
                ):

                    if not chunk:
                        continue

                    content.extend(chunk)

                    if len(content) > MAX_DOWNLOAD_BYTES:

                        raise ValueError(
                            "Download exceeded the 20 MB limit."
                        )

                return {
                    "content": bytes(content),
                    "content_type": response.headers.get(
                        "Content-Type", ""
                    ).lower(),
                    "final_url": response.url
                }

            finally:
                response.close()

        raise ValueError(
            "Too many redirects. Unable to access the paper."
        )

    finally:
        session.close()


# =========================================
# HTML TEXT EXTRACTION
# =========================================

def extract_html_content(html):

    # BeautifulSoup detects webpage encodings.
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # -------------------------------------
    # Extract title
    # -------------------------------------

    title = ""

    if soup.title:
        title = soup.title.get_text(
            " ",
            strip=True
        )

    if not title:

        heading = soup.find("h1")

        if heading:
            title = heading.get_text(
                " ",
                strip=True
            )

    # -------------------------------------
    # Extract author
    # -------------------------------------

    author = ""

    author_meta = soup.find(
        "meta",
        attrs={
            "name": re.compile(
                r"author",
                re.I
            )
        }
    )

    if not author_meta:

        author_meta = soup.find(
            "meta",
            attrs={
                "property": "article:author"
            }
        )

    if not author_meta:

        author_meta = soup.find(
            "meta",
            attrs={
                "name": "citation_author"
            }
        )

    if author_meta:

        author = author_meta.get(
            "content",
            ""
        ).strip()

    # -------------------------------------
    # Extract description
    # -------------------------------------

    description = ""

    description_meta = soup.find(
        "meta",
        attrs={
            "name": "description"
        }
    )

    if not description_meta:

        description_meta = soup.find(
            "meta",
            attrs={
                "property": "og:description"
            }
        )

    if description_meta:

        description = description_meta.get(
            "content",
            ""
        ).strip()

    # -------------------------------------
    # Remove unnecessary elements
    # -------------------------------------

    for element in soup([
        "script",
        "style",
        "noscript",
        "nav",
        "footer",
        "header",
        "aside",
        "form",
        "svg",
        "iframe",
        "button"
    ]):

        element.decompose()

    # -------------------------------------
    # Find main article content
    # -------------------------------------

    content_element = (
        soup.find("article")
        or soup.find("main")
        or soup.find(
            attrs={
                "role": "main"
            }
        )
        or soup.find("body")
        or soup
    )

    # -------------------------------------
    # Prefer the actual Wikipedia article
    # over the broader page container.
    # -------------------------------------

    wikipedia_candidates = soup.select(
        "#mw-content-text .mw-parser-output"
    )

    if wikipedia_candidates:

        content_element = max(
            wikipedia_candidates,
            key=lambda element: len(
                element.get_text(" ", strip=True)
            )
        )

        # Remove Wikipedia navigation, sidebars,
        # disambiguation notes and reference lists.
        wikipedia_noise_selectors = (
            ".navbox",
            ".sidebar",
            ".hatnote",
            ".metadata",
            ".mw-references-wrap",
            ".references",
            ".catlinks",
            ".portal",
            ".noprint"
        )

        for selector in wikipedia_noise_selectors:

            for element in content_element.select(selector):
                element.decompose()

    # -------------------------------------
    # Extract readable text
    # -------------------------------------

        # Extract semantic HTML blocks while preserving their boundaries.
    # Inline elements inside each block are joined with spaces.
    block_tags = (
        "h1", "h2", "h3", "h4", "h5", "h6",
        "p", "li", "blockquote", "pre",
        "dt", "dd", "figcaption", "caption", "tr"
    )

    content_blocks = []

    for element in content_element.find_all(block_tags):

        # Avoid duplicate text from nested semantic blocks.
        if element.find_parent(block_tags):
            continue

        block_text = element.get_text(
            separator=" ",
            strip=True
        )

        block_text = re.sub(
            r"\s+",
            " ",
            block_text
        ).strip()

        if block_text:
            content_blocks.append(block_text)

    if content_blocks:
        text = "\n\n".join(content_blocks)
    else:
        # Fallback for unusual HTML structures.
        text = content_element.get_text(
            separator=" ",
            strip=True
        )

    # -------------------------------------
    # Clean extracted text
    # -------------------------------------

    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    text = text.strip()

    # -------------------------------------
    # Validate extracted content
    # -------------------------------------

    word_count = len(text.split())

    if word_count < MIN_ARTICLE_WORDS:

        raise ValueError(
            "Very little article text was found. "
            "The website may require JavaScript, "
            "a subscription, or direct PDF access."
        )

    if not title:
        title = "Title unavailable"

    if not author:
        author = "Author information unavailable"

    return {
        "title": title,
        "author": author,
        "description": description,
        "full_text": text
    }


# =========================================
# MAIN URL EXTRACTION FUNCTION
# =========================================

def extract_research_url(url):

    if not isinstance(url, str):

        raise ValueError(
            "Please provide a valid research paper URL."
        )

    url = url.strip()

    if not url:

        raise ValueError(
            "Please enter a research paper URL."
        )

    # -------------------------------------
    # Download URL
    # -------------------------------------

    downloaded = download_url(url)

    content = downloaded["content"]

    content_type = downloaded["content_type"]

    final_url = downloaded["final_url"]

    if not content:

        raise ValueError(
            "The website returned an empty response."
        )

    # =====================================
    # DETECT PDF
    # =====================================

    is_pdf = (
        "application/pdf" in content_type
        or content[:5] == b"%PDF-"
        or urlparse(final_url).path.lower().endswith(".pdf")
    )

    if is_pdf:

        try:

            paper_data = extract_pdf(content)

        except Exception as error:

            raise ValueError(
                f"PDF extraction failed: {error}"
            ) from error

        if not paper_data or not paper_data.get("success"):

            raise ValueError(
                "The PDF was downloaded, "
                "but no readable text was extracted."
            )

        paper_data["source_type"] = "URL PDF"

        paper_data["source_url"] = final_url

        return paper_data

    # =====================================
    # DETECT HTML
    # =====================================

    if (
        "text/html" not in content_type
        and "application/xhtml+xml" not in content_type
    ):

        raise ValueError(
            f"Unsupported content type: {content_type}. "
            "Please provide a direct PDF "
            "or article webpage URL."
        )

    # =====================================
    # EXTRACT HTML CONTENT
    # =====================================

    try:

        extracted = extract_html_content(
            content
        )

    except Exception as error:

        raise ValueError(
            f"Webpage text extraction failed: {error}"
        ) from error

    full_text = extracted["full_text"]

    total_words = len(full_text.split())

    # =====================================
    # CREATE PAGE STRUCTURE
    # =====================================

    pages = [
        {
            "page_number": 1,
            "text": full_text,
            "word_count": total_words,
            "character_count": len(full_text),
            "needs_ocr": False,
            "tables": []
        }
    ]

    # =====================================
    # METADATA
    # =====================================

    metadata = {
        "title": extracted["title"],
        "author": extracted["author"],
        "subject": extracted["description"],
        "keywords": "",
        "creator": "",
        "page_count": 1
    }

    # =====================================
    # WARNINGS
    # =====================================

    warnings = [
        "Web article extracted successfully. "
        "Actual PDF page numbers are unavailable "
        "for HTML content."
    ]

    if (
        extracted["author"]
        == "Author information unavailable"
    ):

        warnings.append(
            "Author metadata was not available "
            "on the webpage."
        )

    # =====================================
    # CLASSIFY HTML DOCUMENT
    # =====================================

    hostname = (
        urlparse(final_url).hostname or ""
    ).lower()

    is_wikipedia = (
        hostname == "wikipedia.org"
        or hostname.endswith(".wikipedia.org")
    )

    document_kind = (
        "encyclopedia" if is_wikipedia else "article"
    )

    # =====================================
    # FINAL OUTPUT
    # =====================================

    return {
        "success": bool(full_text.strip()),
        "metadata": metadata,
        "pages": pages,
        "full_text": full_text,
        "total_pages": 1,
        "total_words": total_words,
        "scanned_pages": [],
        "needs_ocr": False,
        "warnings": warnings,
        "extraction_time": 0,
        "source_type": "HTML Article",
        "document_kind": document_kind,
        "source_url": final_url
    }
