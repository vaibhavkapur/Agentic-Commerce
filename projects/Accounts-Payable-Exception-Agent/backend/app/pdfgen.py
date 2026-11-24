"""A tiny dependency-free PDF writer for synthetic fixtures (text-only, Helvetica).

Used by the seed script, the test-suite, and the evaluation corpus generator so that the
extraction pipeline is exercised against real PDF bytes rather than pre-parsed text.
"""

PAGE_WIDTH, PAGE_HEIGHT = 595, 842  # A4 in points
LEFT_MARGIN, TOP_MARGIN, LINE_HEIGHT, FONT_SIZE = 50, 790, 16, 11


def _escape(text: str) -> bytes:
    data = text.encode("cp1252", errors="replace")
    return data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _page_stream(lines: list[str]) -> bytes:
    parts = [b"BT", f"/F1 {FONT_SIZE} Tf".encode(), f"{LINE_HEIGHT} TL".encode()]
    parts.append(f"{LEFT_MARGIN} {TOP_MARGIN} Td".encode())
    for line in lines:
        parts.append(b"(" + _escape(line) + b") Tj T*")
    parts.append(b"ET")
    return b"\n".join(parts)


def build_pdf(pages: list[list[str]], title: str = "Document") -> bytes:
    """Build a PDF where each entry in ``pages`` is a list of text lines for one page."""
    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    pages_id_placeholder = len(objects) + 1 + 2 * len(pages)  # pages object comes after page objs
    page_ids = []
    for lines in pages:
        stream = _page_stream(lines)
        content_id = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page_id = add(
            (
                f"<< /Type /Page /Parent {pages_id_placeholder} 0 R "
                f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode()
        )
        page_ids.append(page_id)
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    pages_id = add(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode())
    assert pages_id == pages_id_placeholder
    catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
    info_id = add(b"<< /Title (" + _escape(title) + b") /Producer (ap-exception-agent) >>")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R /Info {info_id} 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    return bytes(out)
