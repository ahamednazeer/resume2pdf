"""API routes for resume.io to PDF conversion."""

import asyncio


from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Path, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.schemas.resumeio import Extension, PageSize, Quality, Format
from app.services.cache import pdf_cache
from app.services.converter import PDFToDOCXConverter
from app.services.jobs import JobStatus, job_manager
from app.services.resumeio import ResumeioDownloader

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.post("/download/{rendering_token}")
async def download_resume(
    rendering_token: Annotated[str, Path(min_length=24, max_length=24, pattern="^[a-zA-Z0-9]{24}$")],
    image_size: Annotated[int, Query(gt=0)] = 3000,
    extension: Annotated[Extension, Query()] = Extension.jpeg,
    page_size: Annotated[PageSize, Query()] = PageSize.a4,
    quality: Annotated[Quality, Query()] = Quality.max,
    password: Annotated[str | None, Query()] = None,
    format: Annotated[Format, Query()] = Format.pdf,
):
    """Download a resume from resume.io and return it as a PDF or DOCX."""
    # Force PNG extension for Max quality (Lossless)
    if quality == Quality.max:
        extension = Extension.png
        image_size = max(image_size, 4500)  # Verify resolution is at least 4500px

    # Create cache key
    cache_key = f"{rendering_token}:{image_size}:{extension.value}:{page_size.value}:{quality.value}:{password}"

    # Check cache for PDF
    cached_pdf = pdf_cache.get(cache_key)
    if cached_pdf is None:
        # Generate PDF
        resumeio = ResumeioDownloader(
            rendering_token=rendering_token,
            image_size=image_size,
            extension=extension,
            page_size=page_size,
            quality=quality,
            password=password,
        )
        cached_pdf = await resumeio.generate_pdf()
        # Store in cache
        pdf_cache.set(cache_key, cached_pdf)

    # Return based on requested format
    if format == Format.docx:
        converter = PDFToDOCXConverter()
        docx_bytes = converter.convert(cached_pdf)
        return Response(
            docx_bytes,
            headers={
                "Content-Disposition": f'attachment; filename="{rendering_token}.docx"',
            },
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    else:
        return Response(
            cached_pdf,
            headers={
                "Content-Disposition": f'inline; filename="{rendering_token}.pdf"',
                "X-Cache": "HIT" if pdf_cache.get(cache_key) else "MISS",
            },
            media_type="application/pdf",
        )


@router.get("/preview/{rendering_token}")
async def preview_resume(
    rendering_token: Annotated[str, Path(min_length=24, max_length=24, pattern="^[a-zA-Z0-9]{24}$")],
):
    """
    Get a preview image (first page) of the resume.
    """
    resumeio = ResumeioDownloader(rendering_token=rendering_token)
    await resumeio._ResumeioDownloader__get_resume_metadata() # Accessing private method for metadata
    
    # Construct URL for first page with display-friendly size
    preview_url = resumeio.IMAGES_URL.format(
        rendering_token=rendering_token,
        page_id=1,
        extension="jpeg",
        cache_date=resumeio.cache_date,
        image_size=800,
    )
    
    # Fetch image and proxy it back
    response = await resumeio._ResumeioDownloader__get(preview_url)
    
    return Response(
        content=response.content,
        media_type="image/jpeg",
    )


async def _process_pdf_job(
    job_id: str,
    rendering_token: str,
    image_size: int,
    extension: Extension,
    page_size: PageSize,
    quality: Quality,
    password: str | None,
    format: Format,
) -> None:
    """Background task to process PDF generation."""
    # Force PNG extension for Max quality (Lossless)
    if quality == Quality.max:
        extension = Extension.png
        image_size = max(image_size, 4500)

    cache_key = f"{rendering_token}:{image_size}:{extension.value}:{page_size.value}:{quality.value}:{password}"

    try:
        # Update status to processing
        job_manager.update_job(job_id, status=JobStatus.processing, progress=10)

        # Check cache first
        cached_pdf = pdf_cache.get(cache_key)
        if cached_pdf is None:
             # Generate PDF
            job_manager.update_job(job_id, progress=30)
            resumeio = ResumeioDownloader(
                rendering_token=rendering_token,
                image_size=image_size,
                extension=extension,
                page_size=page_size,
                quality=quality,
                password=password,
            )
            job_manager.update_job(job_id, progress=50)
            cached_pdf = await resumeio.generate_pdf()
            
            # Store in cache
            pdf_cache.set(cache_key, cached_pdf)

        # Handle Format
        result_bytes = cached_pdf
        if format == Format.docx:
             job_manager.update_job(job_id, progress=80, message="Converting to DOCX...")
             converter = PDFToDOCXConverter()
             result_bytes = converter.convert(cached_pdf)

        job_manager.update_job(
            job_id,
            status=JobStatus.completed,
            progress=100,
            result=result_bytes,
        )

    except Exception as e:
        job_manager.update_job(
            job_id,
            status=JobStatus.failed,
            error=str(e),
        )


@router.post("/download/{rendering_token}/async")
async def download_resume_async(
    background_tasks: BackgroundTasks,
    rendering_token: Annotated[str, Path(min_length=24, max_length=24, pattern="^[a-zA-Z0-9]{24}$")],
    image_size: Annotated[int, Query(gt=0)] = 3000,
    extension: Annotated[Extension, Query()] = Extension.jpeg,
    page_size: Annotated[PageSize, Query()] = PageSize.a4,
    quality: Annotated[Quality, Query()] = Quality.max,
    password: Annotated[str | None, Query()] = None,
    format: Annotated[Format, Query()] = Format.pdf,
):
    """
    Start an async PDF generation job.

    Returns a job ID that can be used to poll for status.
    """
    # Force PNG extension for Max quality (Lossless)
    if quality == Quality.max:
        extension = Extension.png
        image_size = max(image_size, 4500)

    job = job_manager.create_job(rendering_token)

    # Schedule the background task
    background_tasks.add_task(
        _process_pdf_job,
        job.id,
        rendering_token,
        image_size,
        extension,
        page_size,
        quality,
        password,
        format,
    )

    return JSONResponse(
        content={
            "job_id": job.id,
            "status": job.status.value,
            "message": "PDF generation started. Poll /job/{job_id} for status.",
        },
        status_code=202,
    )


@router.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """
    Get the status of a PDF generation job.

    Returns job status and result if completed.
    """
    job = job_manager.get_job(job_id)

    if job is None:
        return JSONResponse(
            content={"error": "Job not found", "job_id": job_id},
            status_code=404,
        )

    response_data = job.to_dict()

    # If completed, include download URL
    if job.status == JobStatus.completed:
        response_data["download_url"] = f"/job/{job_id}/download"

    return JSONResponse(content=response_data)


@router.get("/job/{job_id}/download")
async def download_job_result(job_id: str):
    """
    Download the result of a completed PDF generation job.
    """
    job = job_manager.get_job(job_id)

    if job is None:
        return JSONResponse(
            content={"error": "Job not found", "job_id": job_id},
            status_code=404,
        )

    if job.status != JobStatus.completed:
        return JSONResponse(
            content={
                "error": "Job not completed",
                "status": job.status.value,
            },
            status_code=400,
        )

    if job.result is None:
        return JSONResponse(
            content={"error": "No result available"},
            status_code=500,
        )

    return Response(
        job.result,
        headers={
            "Content-Disposition": f'inline; filename="{job.token}.pdf"',
        },
        media_type="application/pdf",
    )


@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request):
    """
    Render the main index page.

    Parameters
    ----------
    request : fastapi.Request
        The request instance.

    Returns
    -------
    fastapi.templating.Jinja2Templates.TemplateResponse
        Rendered template of the main index page.
    """
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/health")
async def health_check():
    """Health check endpoint with cache and job stats."""
    return {
        "status": "healthy",
        "cache": pdf_cache.stats(),
        "jobs": job_manager.stats(),
    }
