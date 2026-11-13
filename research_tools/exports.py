from io import BytesIO
import re


def _plain(text):
    text = re.sub(r"```.*?```", "", str(text), flags=re.S)
    text = re.sub(r"[`*_>#]", "", text)
    return text.strip()


def make_docx(title: str, content: str) -> bytes:
    from docx import Document
    document = Document()
    document.add_heading(title, 0)
    for line in str(content).splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("### "):
            document.add_heading(_plain(line[4:]), level=3)
        elif line.startswith("## "):
            document.add_heading(_plain(line[3:]), level=2)
        elif line.startswith("# "):
            document.add_heading(_plain(line[2:]), level=1)
        elif line.startswith(("- ", "* ")):
            document.add_paragraph(_plain(line[2:]), style="List Bullet")
        else:
            document.add_paragraph(_plain(line))
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_pdf(title: str, content: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from xml.sax.saxutils import escape
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
                            topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    story = [Paragraph(escape(title), styles["Title"]), Spacer(1, 8)]
    for line in str(content).splitlines():
        line = line.strip()
        if line:
            story.append(Paragraph(escape(_plain(line)), styles["BodyText"]))
            story.append(Spacer(1, 4))
    doc.build(story)
    return buffer.getvalue()
