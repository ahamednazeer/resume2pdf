"""Custom exception classes for resume2pdf application."""

from fastapi import HTTPException


class ResumeioException(Exception):
    """Base exception for resume.io related errors."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class InvalidTokenError(ResumeioException):
    """Raised when the rendering token format is invalid."""

    def __init__(self, token: str):
        super().__init__(
            message=f"Invalid token format: '{token}'. Token must be a 24-character alphanumeric string.",
            status_code=400,
        )
        self.token = token


class ResumeNotFoundError(ResumeioException):
    """Raised when the resume is not found for the given token."""

    def __init__(self, token: str):
        super().__init__(
            message=f"Resume not found for token: '{token}'. Please verify the token is correct.",
            status_code=404,
        )
        self.token = token


class DownloadError(ResumeioException):
    """Raised when there's an error downloading resume assets."""

    def __init__(self, message: str, original_status: int | None = None):
        super().__init__(
            message=f"Download failed: {message}",
            status_code=502,
        )
        self.original_status = original_status


class PDFGenerationError(ResumeioException):
    """Raised when PDF generation fails."""

    def __init__(self, message: str):
        super().__init__(
            message=f"PDF generation failed: {message}",
            status_code=500,
        )
