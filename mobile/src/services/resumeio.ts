/**
 * Resume.io API Service
 * Ports the Python ResumeioDownloader to TypeScript for client-side use
 */

import { CapacitorHttp } from '@capacitor/core';
import type { HttpResponse } from '@capacitor/core';

export interface PageMetadata {
    viewport: { width: number; height: number };
    links: Array<{
        url: string;
        x: number;
        y: number;
        width: number;
        height: number;
    }>;
}

export interface ResumeMetadata {
    pages: PageMetadata[];
}

export type Extension = 'jpeg' | 'png' | 'webp';
export type PageSize = 'a4' | 'letter' | 'legal' | 'original';
export type Quality = 'low' | 'medium' | 'high' | 'max';

// Page dimensions in points (width, height)
export const PAGE_DIMENSIONS: Record<string, [number, number]> = {
    a4: [595, 842],
    letter: [612, 792],
    legal: [612, 1008],
};

export class ResumeioService {
    private renderingToken: string;
    private extension: Extension;
    private imageSize: number;
    private cacheDate: string;

    private readonly METADATA_URL = 'https://ssr.resume.tools/meta/{token}?cache={cache}';
    private readonly IMAGES_URL = 'https://ssr.resume.tools/to-image/{token}-{page}.{ext}?cache={cache}&size={size}';

    constructor(
        renderingToken: string,
        extension: Extension = 'jpeg',
        imageSize: number = 3000
    ) {
        this.renderingToken = renderingToken;
        this.extension = extension;
        this.imageSize = imageSize;
        this.cacheDate = new Date().toISOString().slice(0, -10) + 'Z';
    }

    /**
     * Fetch resume metadata from resume.io
     */
    async getMetadata(): Promise<PageMetadata[]> {
        const url = this.METADATA_URL
            .replace('{token}', this.renderingToken)
            .replace('{cache}', this.cacheDate);

        const response: HttpResponse = await CapacitorHttp.get({
            url,
            headers: {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36'
            }
        });

        if (response.status === 404) {
            throw new Error('Resume not found. Please check your renderingToken.');
        }

        if (response.status !== 200) {
            throw new Error(`Failed to fetch metadata: HTTP ${response.status}`);
        }

        const data = response.data as ResumeMetadata;
        if (!data.pages || data.pages.length === 0) {
            throw new Error('Resume not found or has no pages.');
        }

        return data.pages;
    }

    /**
     * Download a single page image
     */
    async downloadImage(pageId: number): Promise<Uint8Array> {
        const url = this.IMAGES_URL
            .replace('{token}', this.renderingToken)
            .replace('{page}', pageId.toString())
            .replace('{ext}', this.extension)
            .replace('{cache}', this.cacheDate)
            .replace('{size}', this.imageSize.toString());

        const response: HttpResponse = await CapacitorHttp.get({
            url,
            responseType: 'arraybuffer',
            headers: {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36'
            }
        });

        if (response.status !== 200) {
            throw new Error(`Failed to download page ${pageId}: HTTP ${response.status}`);
        }

        // Convert base64 response to Uint8Array
        const binaryString = atob(response.data);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        return bytes;
    }

    /**
     * Download all page images in parallel
     */
    async downloadAllImages(pageCount: number, onProgress?: (current: number, total: number) => void): Promise<Uint8Array[]> {
        const images: Uint8Array[] = [];

        for (let i = 1; i <= pageCount; i++) {
            const imageData = await this.downloadImage(i);
            images.push(imageData);
            if (onProgress) {
                onProgress(i, pageCount);
            }
        }

        return images;
    }

    /**
     * Get preview image URL for first page
     */
    getPreviewUrl(): string {
        return this.IMAGES_URL
            .replace('{token}', this.renderingToken)
            .replace('{page}', '1')
            .replace('{ext}', this.extension)
            .replace('{cache}', this.cacheDate)
            .replace('{size}', '1000');
    }
}
