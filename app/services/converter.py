"""Service to convert PDF to DOCX."""

import io
import os
import tempfile
from dataclasses import dataclass

from pdf2docx import Converter


@dataclass
class PDFToDOCXConverter:
    """Service to convert PDF bytes to DOCX bytes."""

    def convert(self, pdf_bytes: bytes) -> bytes:
        """
        Convert PDF bytes to DOCX bytes.

        Parameters
        ----------
        pdf_bytes : bytes
            The PDF content.

        Returns
        -------
        bytes
            The conversion result as DOCX bytes.
        """
        # Create temp files for input PDF and output DOCX
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
            temp_pdf.write(pdf_bytes)
            temp_pdf_path = temp_pdf.name

        temp_docx_path = temp_pdf_path.replace(".pdf", ".docx")

        try:
            # Run conversion
            cv = Converter(temp_pdf_path)
            cv.convert(temp_docx_path, start=0, end=None)
            cv.close()

            # Read result
            with open(temp_docx_path, "rb") as f:
                docx_bytes = f.read()

            return docx_bytes

        finally:
            # Cleanup temp files
            if os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)
            if os.path.exists(temp_docx_path):
                os.remove(temp_docx_path)
