import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytesseract
import requests
from fastapi import HTTPException
from PIL import Image
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.annotations import Link

from app.schemas.resumeio import Extension, PageSize, PAGE_DIMENSIONS


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
    """

    rendering_token: str
    extension: Extension = Extension.jpeg
    image_size: int = 3000
    page_size: PageSize = PageSize.a4
    METADATA_URL: str = field(default="https://ssr.resume.tools/meta/{rendering_token}?cache={cache_date}", repr=False)
    IMAGES_URL: str = field(default=(
        "https://ssr.resume.tools/to-image/{rendering_token}-{page_id}.{extension}?cache={cache_date}&size={image_size}"
    ), repr=False)

    def __post_init__(self) -> None:
        """Set the cache date to the current time."""
        self.cache_date = datetime.now(timezone.utc).isoformat()[:-10] + "Z"

    def generate_pdf(self) -> bytes:
        """
        Generate a PDF from the resume.io resume.

        Returns
        -------
        bytes
            PDF representation of the resume.
        """
        self.__get_resume_metadata()
        images = self.__download_images()
        pdf = PdfWriter()
        metadata_w, metadata_h = self.metadata[0].get("viewport").values()

        for i, image in enumerate(images):
            page_pdf = pytesseract.image_to_pdf_or_hocr(Image.open(image), extension="pdf", config="--dpi 300")
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

        with io.BytesIO() as file:
            pdf.write(file)
            return file.getvalue()

    def __get_resume_metadata(self) -> None:
        """Download the metadata for the resume."""
        response = self.__get(
            self.METADATA_URL.format(rendering_token=self.rendering_token, cache_date=self.cache_date),
        )
        content: dict[str, list] = json.loads(response.text)
        self.metadata = content.get("pages")

    def __download_images(self) -> list[io.BytesIO]:
        """Download the images for the resume.

        Returns
        -------
        list[io.BytesIO]
            List of image files.
        """
        images = []
        for page_id in range(1, 1 + len(self.metadata)):
            image_url = self.IMAGES_URL.format(
                rendering_token=self.rendering_token,
                page_id=page_id,
                extension=self.extension.value,
                cache_date=self.cache_date,
                image_size=self.image_size,
            )
            response = self.__get(image_url)
            images.append(io.BytesIO(response.content))

        return images

    def __get(self, url: str) -> requests.Response:
        """Get a response from a URL.

        Parameters
        ----------
        url : str
            URL to get.

        Returns
        -------
        requests.Response
            Response object.

        Raises
        ------
        HTTPException
            If the response status code is not 200.
        """
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36",
            },
        )
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Unable to download resume (rendering token: {self.rendering_token})",
            )
        return response
