from enum import Enum


class Extension(str, Enum):
    jpeg = "jpeg"
    png = "png"
    webp = "webp"


class PageSize(str, Enum):
    """
    Page size options for PDF output.
    Dimensions are in points (72 points = 1 inch).
    """
    original = "original"  # Keep original dimensions from resume.io
    a4 = "a4"              # 210mm × 297mm = 595 × 842 points
    letter = "letter"      # 8.5" × 11" = 612 × 792 points
    legal = "legal"        # 8.5" × 14" = 612 × 1008 points


class Format(str, Enum):
    pdf = "pdf"
    docx = "docx"


class Quality(str, Enum):
    low = "low"        # JPEG 50%
    medium = "medium"  # JPEG 75%
    high = "high"      # JPEG 95%
    max = "max"        # PNG (Lossless)


# Page dimensions in points (width, height)
PAGE_DIMENSIONS = {
    PageSize.a4: (595, 842),
    PageSize.letter: (612, 792),
    PageSize.legal: (612, 1008),
}
