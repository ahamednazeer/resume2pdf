/**
 * PDF Generator Service
 * Creates PDFs from images with embedded hyperlinks using pdf-lib
 */

import { PDFDocument, PDFName, PDFArray } from 'pdf-lib';
import type { PageMetadata, PageSize, Quality } from './resumeio';
import { PAGE_DIMENSIONS } from './resumeio';

export interface PDFGeneratorOptions {
    pageSize: PageSize;
    quality: Quality;
    password?: string;
}

export class PDFGenerator {
    private options: PDFGeneratorOptions;

    constructor(options: PDFGeneratorOptions) {
        this.options = options;
    }

    /**
     * Generate PDF from images with hyperlinks
     */
    async generatePDF(
        images: Uint8Array[],
        metadata: PageMetadata[],
        onProgress?: (current: number, total: number) => void
    ): Promise<Uint8Array> {
        const pdfDoc = await PDFDocument.create();

        for (let i = 0; i < images.length; i++) {
            const imageBytes = images[i];
            const pageMetadata = metadata[i];

            // Embed the JPEG image
            const image = await pdfDoc.embedJpg(imageBytes);
            const imgWidth = image.width;
            const imgHeight = image.height;

            // Get metadata viewport dimensions
            const metadataW = pageMetadata.viewport.width;
            const metadataH = pageMetadata.viewport.height;

            // Determine target page size
            let targetWidth: number;
            let targetHeight: number;
            let scale: number;
            let offsetX = 0;
            let offsetY = 0;

            if (this.options.pageSize === 'original' || !PAGE_DIMENSIONS[this.options.pageSize]) {
                // Use original dimensions from metadata
                targetWidth = metadataW;
                targetHeight = metadataH;
                scale = Math.min(targetWidth / imgWidth, targetHeight / imgHeight);
            } else {
                // Use specified page size
                [targetWidth, targetHeight] = PAGE_DIMENSIONS[this.options.pageSize];

                // Calculate scale to fit content while maintaining aspect ratio
                const scaleX = targetWidth / imgWidth;
                const scaleY = targetHeight / imgHeight;
                scale = Math.min(scaleX, scaleY);
            }

            // Calculate actual dimensions after scaling
            const scaledWidth = imgWidth * scale;
            const scaledHeight = imgHeight * scale;

            // Center the image on the page
            offsetX = (targetWidth - scaledWidth) / 2;
            offsetY = (targetHeight - scaledHeight) / 2;

            // Add page with target dimensions
            const page = pdfDoc.addPage([targetWidth, targetHeight]);

            // Draw the image
            page.drawImage(image, {
                x: offsetX,
                y: offsetY,
                width: scaledWidth,
                height: scaledHeight,
            });

            if (onProgress) {
                onProgress(i + 1, images.length);
            }
        }

        // Add hyperlinks properly using pdf-lib annotations
        await this.addHyperlinks(pdfDoc, metadata);

        // Generate PDF bytes
        const pdfBytes = await pdfDoc.save();
        return new Uint8Array(pdfBytes);
    }

    /**
     * Add hyperlink annotations to PDF pages
     */
    private async addHyperlinks(
        pdfDoc: PDFDocument,
        metadata: PageMetadata[]
    ): Promise<void> {
        const pages = pdfDoc.getPages();

        for (let i = 0; i < metadata.length && i < pages.length; i++) {
            const page = pages[i];
            const pageMetadata = metadata[i];
            const { height: pageHeight } = page.getSize();
            const metadataH = pageMetadata.viewport.height;

            // Calculate scale factor
            const linkScale = pageHeight / metadataH;

            // Create annotations array for this page
            const annotations: any[] = [];

            for (const link of pageMetadata.links) {
                const x1 = link.x * linkScale;
                const y1 = pageHeight - (link.y * linkScale) - (link.height * linkScale);
                const x2 = x1 + (link.width * linkScale);
                const y2 = y1 + (link.height * linkScale);

                // Create link annotation
                const linkAnnotation = pdfDoc.context.obj({
                    Type: 'Annot',
                    Subtype: 'Link',
                    Rect: [x1, y1, x2, y2],
                    Border: [0, 0, 0],
                    A: {
                        Type: 'Action',
                        S: 'URI',
                        URI: link.url,
                    },
                });

                const annotRef = pdfDoc.context.register(linkAnnotation);
                annotations.push(annotRef);
            }

            if (annotations.length > 0) {
                // Get the page dictionary and add annotations
                const pageDict = page.node;
                const annotsKey = PDFName.of('Annots');

                // Check if page already has annotations
                const existingAnnots = pageDict.get(annotsKey);
                if (existingAnnots instanceof PDFArray) {
                    annotations.forEach(a => existingAnnots.push(a));
                } else {
                    pageDict.set(annotsKey, pdfDoc.context.obj(annotations));
                }
            }
        }
    }
}
