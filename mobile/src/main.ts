/**
 * Resume2PDF Mobile App - Main Entry Point
 * Handles form submission, PDF generation, and file saving
 */

import './style.css';
import { Filesystem, Directory } from '@capacitor/filesystem';
import { Share } from '@capacitor/share';
import { Haptics, ImpactStyle } from '@capacitor/haptics';
import { ResumeioService } from './services/resumeio';
import type { PageSize, Quality } from './services/resumeio';
import { PDFGenerator } from './services/pdf-generator';

// DOM Elements
const downloadForm = document.getElementById('downloadForm') as HTMLFormElement;
const errorMessage = document.querySelector('.error') as HTMLElement;
const inputField = document.querySelector('.resume') as HTMLInputElement;
const historyList = document.getElementById('historyList') as HTMLElement;
const historyContainer = document.querySelector('.history-container') as HTMLElement;
const previewModal = document.getElementById('previewModal') as HTMLElement;
const previewImage = document.getElementById('previewImage') as HTMLImageElement;
const previewLoader = document.getElementById('previewLoader') as HTMLElement;
const closePreviewBtn = document.getElementById('closePreviewBtn') as HTMLElement;
const previewBtn = document.getElementById('previewBtn') as HTMLElement;
const submitBtn = document.getElementById('submit-btn') as HTMLButtonElement;
const submitText = document.getElementById('submit-text') as HTMLElement;
const loader = document.getElementById('loader') as HTMLElement;
const progressContainer = document.getElementById('progressContainer') as HTMLElement;
const progressFill = document.getElementById('progressFill') as HTMLElement;
const progressText = document.getElementById('progressText') as HTMLElement;

// Token validation regex
const TOKEN_REGEX = /^[a-zA-Z0-9]{24}$/;

/**
 * Validate rendering token format
 */
function validateToken(token: string): boolean {
  return TOKEN_REGEX.test(token);
}

/**
 * Show error state on input
 */
function showError(): void {
  errorMessage.style.display = 'block';
  inputField.classList.add('error-border');
  inputField.classList.remove('shake');
  setTimeout(() => inputField.classList.add('shake'), 100);
  Haptics.impact({ style: ImpactStyle.Medium });
}

/**
 * Clear error state
 */
function clearError(): void {
  errorMessage.style.display = 'none';
  inputField.classList.remove('error-border', 'shake');
}

/**
 * Show toast notification
 */
function showToast(message: string, type: 'success' | 'error' = 'success'): void {
  const existingToast = document.querySelector('.toast');
  if (existingToast) {
    existingToast.remove();
  }

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => toast.classList.add('show'), 10);
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

/**
 * Update progress indicator
 */
function updateProgress(current: number, total: number, status: string): void {
  const percent = Math.round((current / total) * 100);
  progressFill.style.width = `${percent}%`;
  progressText.textContent = status;
}

/**
 * Set loading state
 */
function setLoading(loading: boolean): void {
  if (loading) {
    submitText.style.display = 'none';
    loader.style.display = 'block';
    submitBtn.disabled = true;
    progressContainer.style.display = 'flex';
    progressFill.style.width = '0%';
  } else {
    submitText.style.display = 'block';
    loader.style.display = 'none';
    submitBtn.disabled = false;
    progressContainer.style.display = 'none';
  }
}

/**
 * Add token to history
 */
function addToHistory(token: string): void {
  let history = JSON.parse(localStorage.getItem('resume_history') || '[]');
  history = history.filter((h: { token: string }) => h.token !== token);
  history.unshift({
    token: token,
    date: new Date().toLocaleDateString()
  });
  if (history.length > 5) history.pop();
  localStorage.setItem('resume_history', JSON.stringify(history));
  updateHistoryList();
}

/**
 * Update history list display
 */
function updateHistoryList(): void {
  const history = JSON.parse(localStorage.getItem('resume_history') || '[]');
  if (history.length === 0) {
    historyContainer.style.display = 'none';
    return;
  }
  historyContainer.style.display = 'block';
  historyList.innerHTML = history.map((item: { token: string; date: string }) => `
    <div class="history-item" data-token="${item.token}">
      <span>${item.token}</span>
      <span style="font-size: 0.8rem; color: #999;">${item.date}</span>
    </div>
  `).join('');

  // Add click handlers
  historyList.querySelectorAll('.history-item').forEach(item => {
    item.addEventListener('click', () => {
      const token = item.getAttribute('data-token');
      if (token) {
        inputField.value = token;
        Haptics.impact({ style: ImpactStyle.Light });
      }
    });
  });
}

/**
 * Close preview modal
 */
function closePreview(): void {
  previewModal.style.display = 'none';
  previewImage.src = '';
  previewImage.style.display = 'none';
  previewLoader.style.display = 'none';
}

/**
 * Handle preview button click
 */
async function handlePreview(): Promise<void> {
  const formData = new FormData(downloadForm);
  const token = formData.get('rendering_token')?.toString() || '';

  if (!validateToken(token)) {
    showError();
    return;
  }

  previewModal.style.display = 'flex';
  previewImage.style.display = 'none';
  previewLoader.style.display = 'block';

  try {
    const service = new ResumeioService(token);
    const previewUrl = service.getPreviewUrl();

    previewImage.onload = () => {
      previewLoader.style.display = 'none';
      previewImage.style.display = 'block';
    };
    previewImage.onerror = () => {
      showToast('Could not load preview. Token might be invalid.', 'error');
      closePreview();
    };
    previewImage.src = previewUrl;
  } catch (e) {
    showToast('Error loading preview', 'error');
    closePreview();
  }
}

/**
 * Handle form submission - generate and save PDF
 */
async function handleSubmit(e: Event): Promise<void> {
  e.preventDefault();

  const formData = new FormData(downloadForm);
  const token = formData.get('rendering_token')?.toString() || '';
  const pageSize = (document.getElementById('page_size') as HTMLSelectElement).value as PageSize;
  const quality = (document.getElementById('quality') as HTMLSelectElement).value as Quality;
  const password = (document.getElementById('password') as HTMLInputElement).value;

  if (!validateToken(token)) {
    showError();
    return;
  }

  clearError();
  setLoading(true);
  Haptics.impact({ style: ImpactStyle.Medium });

  try {
    // Add to history
    addToHistory(token);

    // Step 1: Get metadata
    updateProgress(0, 4, 'Fetching resume info...');
    const service = new ResumeioService(token);
    const metadata = await service.getMetadata();

    // Step 2: Download images
    updateProgress(1, 4, `Downloading ${metadata.length} page(s)...`);
    const images = await service.downloadAllImages(metadata.length, (current, total) => {
      updateProgress(1 + (current / total), 4, `Downloading page ${current}/${total}...`);
    });

    // Step 3: Generate PDF
    updateProgress(2, 4, 'Generating PDF...');
    const generator = new PDFGenerator({ pageSize, quality, password: password || undefined });
    const pdfBytes = await generator.generatePDF(images, metadata);

    // Step 4: Save file
    updateProgress(3, 4, 'Saving PDF...');
    const fileName = `resume_${token.substring(0, 8)}_${Date.now()}.pdf`;

    // Convert to base64 for Capacitor Filesystem
    const base64 = btoa(
      pdfBytes.reduce((data, byte) => data + String.fromCharCode(byte), '')
    );

    await Filesystem.writeFile({
      path: fileName,
      data: base64,
      directory: Directory.Documents,
    });

    updateProgress(4, 4, 'Done!');
    Haptics.impact({ style: ImpactStyle.Heavy });
    showToast(`PDF saved: ${fileName}`, 'success');

    // Offer to share
    setTimeout(async () => {
      const result = await Filesystem.getUri({
        path: fileName,
        directory: Directory.Documents,
      });

      await Share.share({
        title: 'Resume PDF',
        url: result.uri,
        dialogTitle: 'Share your resume',
      });
    }, 500);

  } catch (error) {
    console.error('Error generating PDF:', error);
    const errorMsg = error instanceof Error ? error.message : 'Failed to generate PDF';
    showToast(errorMsg, 'error');
    Haptics.impact({ style: ImpactStyle.Heavy });
  } finally {
    setLoading(false);
  }
}

// Event Listeners
downloadForm.addEventListener('submit', handleSubmit);
previewBtn.addEventListener('click', handlePreview);
closePreviewBtn.addEventListener('click', closePreview);
previewModal.addEventListener('click', (e) => {
  if (e.target === previewModal) closePreview();
});

// Clear error on input
inputField.addEventListener('input', clearError);

// Initialize history
updateHistoryList();
