"""Main application module for Resume.io to PDF converter."""

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.api import router
from app.exceptions import (
    DownloadError,
    InvalidTokenError,
    PDFGenerationError,
    ResumeioException,
    ResumeNotFoundError,
)

app = FastAPI(
    title="Resume.io to PDF",
    description="Download your resume from resume.io as a PDF file",
    version="2.0.0",
)


# Exception handlers
@app.exception_handler(InvalidTokenError)
async def invalid_token_handler(request: Request, exc: InvalidTokenError):
    """Handle invalid token format errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "invalid_token",
            "message": exc.message,
            "token": exc.token,
        },
    )


@app.exception_handler(ResumeNotFoundError)
async def resume_not_found_handler(request: Request, exc: ResumeNotFoundError):
    """Handle resume not found errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "resume_not_found",
            "message": exc.message,
            "token": exc.token,
        },
    )


@app.exception_handler(DownloadError)
async def download_error_handler(request: Request, exc: DownloadError):
    """Handle download errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "download_failed",
            "message": exc.message,
            "original_status": exc.original_status,
        },
    )


@app.exception_handler(PDFGenerationError)
async def pdf_generation_error_handler(request: Request, exc: PDFGenerationError):
    """Handle PDF generation errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "pdf_generation_failed",
            "message": exc.message,
        },
    )


@app.exception_handler(ResumeioException)
async def resumeio_exception_handler(request: Request, exc: ResumeioException):
    """Handle generic resume.io exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "resumeio_error",
            "message": exc.message,
        },
    )


# Include router
app.include_router(router)


if __name__ == "__main__":
    """Instantiate the application webserver"""
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["app", "templates"])
