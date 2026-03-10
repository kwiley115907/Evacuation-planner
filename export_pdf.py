from __future__ import annotations

from typing import Tuple

def export_plan_pdf(
    pdf_path: str,
    sheet_image_path: str,
    title: str,
    footer_text: str,
) -> Tuple[bool, str]:
    """
    Saves a 1-page PDF that contains the already-baked "sheet" PNG.
    Returns (ok, error_message).
    """
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.lib.utils import ImageReader
    except Exception as e:
        return (False, f"ReportLab not available: {e}")

    try:
        page_w, page_h = landscape(letter)
        c = canvas.Canvas(pdf_path, pagesize=(page_w, page_h))

        img = ImageReader(sheet_image_path)
        iw, ih = img.getSize()

        # Fit to page with margins
        margin = 36
        avail_w = page_w - 2 * margin
        avail_h = page_h - 2 * margin

        scale = min(avail_w / iw, avail_h / ih)
        draw_w = iw * scale
        draw_h = ih * scale

        x = (page_w - draw_w) / 2
        y = (page_h - draw_h) / 2

        c.drawImage(img, x, y, width=draw_w, height=draw_h)

        # Simple PDF footer (extra safety)
        c.setFont("Helvetica", 10)
        c.drawString(margin, 12, footer_text)

        c.showPage()
        c.save()
        return (True, "")
    except Exception as e:
        return (False, str(e))
