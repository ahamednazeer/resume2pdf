"""Service to download resumes from resume.io and convert to PDF."""

import asyncio
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
import pytesseract
from PIL import Image
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.annotations import Link

from app.exceptions import DownloadError, PDFGenerationError, ResumeNotFoundError
from app.schemas.resumeio import PAGE_DIMENSIONS, Extension, PageSize, Quality


@dataclass
class ResumeioDownloader:
    """
    Class to download a resume from resume.io and convert it to a PDF.

    Parameters
    ----------
    rendering_token : str
        Rendering Token of the resume to download.
    extension : Extension, optional
        Image extension to download, by default "jpeg".
    image_size : int, optional
        Size of the images to download, by default 3000.
    page_size : PageSize, optional
        Target page size for the PDF, by default "a4".
    quality : Quality, optional
        Quality of the output PDF images, by default "medium".
    password : str | None, optional
        Password to encrypt the PDF, by default None.
    """

    rendering_token: str
    extension: Extension = Extension.jpeg
    image_size: int = 3000
    page_size: PageSize = PageSize.a4
    quality: Quality = Quality.max
    password: str | None = None
    METADATA_URL: str = field(default="https://ssr.resume.tools/meta/{rendering_token}?cache={cache_date}", repr=False)
    IMAGES_URL: str = field(
        default=(
            "https://ssr.resume.tools/to-image/{rendering_token}-{page_id}.{extension}?cache={cache_date}&size={image_size}"
        ),
        repr=False,
    )

    def __post_init__(self) -> None:
        """Set the cache date to the current time."""
        self.cache_date = datetime.now(timezone.utc).isoformat()[:-10] + "Z"
        self.metadata: list[dict] = []

    async def generate_pdf(self) -> bytes:
        """
        Generate a PDF from the resume.io resume.

        Returns
        -------
        bytes
            PDF representation of the resume.

        Raises
        ------
        ResumeNotFoundError
            If the resume is not found.
        DownloadError
            If there's an error downloading assets.
        PDFGenerationError
            If PDF generation fails.
        """
        await self.__get_resume_metadata()
        images = await self.__download_images()

        try:
            pdf = PdfWriter()
            metadata_w, metadata_h = self.metadata[0].get("viewport").values()

            # Prepare image save options based on quality
            save_kwargs = {}
            if self.quality != Quality.max:
                save_kwargs["optimize"] = True
                if self.quality == Quality.low:
                    save_kwargs["quality"] = 50
                elif self.quality == Quality.medium:
                    save_kwargs["quality"] = 75
                elif self.quality == Quality.high:
                    save_kwargs["quality"] = 95

            for i, image in enumerate(images):
                # Compress image if needed before PDF conversion
                img = Image.open(image)
                if self.quality != Quality.max:
                    img_buffer = io.BytesIO()
                    img.save(img_buffer, format="JPEG", **save_kwargs)
                    img = Image.open(img_buffer)

                # Calculate DPI dynamically to prevent downscaling
                # Page dimensions are in points (1/72 inch)
                # We use the metadata viewport width as the reference for "natural" size
                current_img_width_px = img.width
                # Default to A4 width in points if metadata missing (unlikely)
                page_width_pt = metadata_w if metadata_w else 595 
                
                # DPI = (Pixels / Points) * 72
                calculated_dpi = int((current_img_width_px / page_width_pt) * 72)
                
                # Ensure acceptable minimum DPI (e.g. 72)
                calculated_dpi = max(calculated_dpi, 72)

                page_pdf = pytesseract.image_to_pdf_or_hocr(
                    img, 
                    extension="pdf", 
                    config=f"--dpi {calculated_dpi}"
                )
                page = PdfReader(io.BytesIO(page_pdf)).pages[0]

                # Get original page dimensions
                orig_width = float(page.mediabox.width)
                orig_height = float(page.mediabox.height)

                # Calculate scale for link positioning (based on metadata)
                page_scale = max(orig_height / metadata_h, orig_width / metadata_w)

                # Apply page size transformation if not original
                if self.page_size != PageSize.original and self.page_size in PAGE_DIMENSIONS:
                    target_width, target_height = PAGE_DIMENSIONS[self.page_size]

                    # Calculate scale to fit content in target page size while maintaining aspect ratio
                    scale_x = target_width / orig_width
                    scale_y = target_height / orig_height
                    scale = min(scale_x, scale_y)  # Fit within bounds

                    # Calculate centering offsets
                    new_width = orig_width * scale
                    new_height = orig_height * scale
                    offset_x = (target_width - new_width) / 2
                    offset_y = (target_height - new_height) / 2

                    # Apply transformation: scale and translate
                    transform = Transformation().scale(scale, scale).translate(offset_x, offset_y)
                    page.add_transformation(transform)

                    # Update mediabox to target size
                    page.mediabox.lower_left = (0, 0)
                    page.mediabox.upper_right = (target_width, target_height)

                    # Update link scale for the scaled page
                    link_scale = page_scale * scale
                    link_offset_x = offset_x
                    link_offset_y = offset_y
                else:
                    link_scale = page_scale
                    link_offset_x = 0
                    link_offset_y = 0

                pdf.add_page(page)

                for link in self.metadata[i].get("links"):
                    link_url = link.pop("url")
                    link.update((k, v * link_scale) for k, v in link.items())
                    x, y, w, h = link.values()

                    # Apply offset for centered content
                    x += link_offset_x
                    y += link_offset_y

                    link_annotation = Link(rect=(x, y, x + w, y + h), url=link_url)
                    pdf.add_annotation(page_number=i, annotation=link_annotation)

            # Encrypt PDF if password provided
            if self.password:
                pdf.encrypt(self.password)

            with io.BytesIO() as file:
                pdf.write(file)
                return file.getvalue()

        except Exception as e:
            raise PDFGenerationError(str(e)) from e

    async def __get_resume_metadata(self) -> None:
        """Download the metadata for the resume."""
        url = self.METADATA_URL.format(rendering_token=self.rendering_token, cache_date=self.cache_date)
        response = await self.__get(url)
        content: dict[str, list] = json.loads(response.text)
        self.metadata = content.get("pages", [])

        if not self.metadata:
            raise ResumeNotFoundError(self.rendering_token)

    async def __download_images(self) -> list[io.BytesIO]:
        """
        Download the images for the resume in parallel.

        Returns
        -------
        list[io.BytesIO]
            List of image files.
        """

        async def download_single_image(page_id: int) -> io.BytesIO:
            image_url = self.IMAGES_URL.format(
                rendering_token=self.rendering_token,
                page_id=page_id,
                extension=self.extension.value,
                cache_date=self.cache_date,
                image_size=self.image_size,
            )
            response = await self.__get(image_url)
            return io.BytesIO(response.content)

        # Download all images in parallel
        tasks = [download_single_image(page_id) for page_id in range(1, 1 + len(self.metadata))]
        images = await asyncio.gather(*tasks)
        return list(images)

    async def __get(self, url: str) -> httpx.Response:
        """
        Get a response from a URL asynchronously.

        Parameters
        ----------
        url : str
            URL to get.

        Returns
        -------
        httpx.Response
            Response object.

        Raises
        ------
        ResumeNotFoundError
            If the resume is not found (404).
        DownloadError
            If the request fails.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/136.0.0.0 Safari/537.36",
                    },
                )

                if response.status_code == 404:
                    raise ResumeNotFoundError(self.rendering_token)

                if response.status_code != 200:
                    raise DownloadError(
                        f"Server returned status {response.status_code}",
                        original_status=response.status_code,
                    )

                return response

            except httpx.TimeoutException as e:
                raise DownloadError("Request timed out. Please try again.") from e
            except httpx.RequestError as e:
                raise DownloadError(f"Network error: {str(e)}") from e
