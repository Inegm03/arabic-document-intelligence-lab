import * as pdfjsLib from 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.8.69/pdf.min.mjs';

pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.8.69/pdf.worker.min.mjs';

const fileInput = document.querySelector('#fileInput');
const preview = document.querySelector('#preview');
const prompt = document.querySelector('#uploadPrompt');
const ctx = preview.getContext('2d', { willReadFrequently: true });
const pdfControls = document.querySelector('#pdfControls');
const pageIndicator = document.querySelector('#pageIndicator');
const previousPage = document.querySelector('#previousPage');
const nextPage = document.querySelector('#nextPage');
const runOcrButton = document.querySelector('#runOcrButton');
const downloadTextButton = document.querySelector('#downloadTextButton');
const downloadJsonButton = document.querySelector('#downloadJsonButton');
const ocrProgress = document.querySelector('#ocrProgress');
const ocrProgressBar = document.querySelector('#ocrProgressBar');
const ocrConfidence = document.querySelector('#ocrConfidence');
const els = {
  score: document.querySelector('#score'), ring: document.querySelector('#scoreRing'),
  brightness: document.querySelector('#brightness'), contrast: document.querySelector('#contrast'),
  sharpness: document.querySelector('#sharpness'), status: document.querySelector('#status'),
  text: document.querySelector('#ocrText'), type: document.querySelector('#docType')
};
let pdfDocument = null;
let currentPage = 1;
let renderToken = 0;
let ocrWorker = null;
let currentFilename = 'arabic-document';
let lastOcrResult = null;

function setOutput(text) { els.text.value = text; }

function resetOcrResult() {
  lastOcrResult = null;
  ocrProgress.textContent = 'OCR ready'; ocrProgressBar.value = 0; ocrConfidence.textContent = '—';
  downloadTextButton.disabled = true; downloadJsonButton.disabled = true;
}

function setMetric(name, value) {
  els[name].textContent = `${Math.round(value)}%`;
  document.querySelector(`#${name}Bar`).style.width = `${Math.max(4, Math.min(100, value))}%`;
}

function analyse() {
  const w = preview.width, h = preview.height;
  const data = ctx.getImageData(0, 0, w, h).data;
  let sum = 0, sq = 0, edges = 0;
  const count = w * h;
  const gray = new Uint8Array(count);
  for (let i = 0, p = 0; i < data.length; i += 4, p++) {
    const g = .299 * data[i] + .587 * data[i + 1] + .114 * data[i + 2];
    gray[p] = g; sum += g; sq += g * g;
  }
  const mean = sum / count;
  const std = Math.sqrt(sq / count - mean * mean);
  for (let y = 1; y < h - 1; y += 2) for (let x = 1; x < w - 1; x += 2) {
    const p = y * w + x;
    edges += Math.abs(4 * gray[p] - gray[p - 1] - gray[p + 1] - gray[p - w] - gray[p + w]);
  }
  const brightness = 100 - Math.min(100, Math.abs(mean - 180) / 1.5);
  const contrast = Math.min(100, std * 2.1);
  const sharpness = Math.min(100, edges / (count / 4) * 1.7);
  const score = Math.round(brightness * .3 + contrast * .3 + sharpness * .4);
  setMetric('brightness', brightness); setMetric('contrast', contrast); setMetric('sharpness', sharpness);
  els.score.textContent = score;
  els.ring.style.strokeDasharray = `${score} 100`;
  els.status.textContent = score > 74 ? 'Good quality' : score > 50 ? 'Review advised' : 'Poor quality';
  setOutput('تم تحليل جودة الصفحة بنجاح. اضغط «استخراج النص العربي» لتشغيل التعرّف الضوئي محلياً.');
}

function showPreview() {
  preview.style.display = 'block';
  prompt.style.display = 'none';
  runOcrButton.disabled = false;
  resetOcrResult();
}

function updatePdfControls() {
  pdfControls.hidden = !pdfDocument;
  if (!pdfDocument) return;
  pageIndicator.textContent = `Page ${currentPage} of ${pdfDocument.numPages}`;
  previousPage.disabled = currentPage === 1;
  nextPage.disabled = currentPage === pdfDocument.numPages;
}

function drawImage(img) {
  // Keep the source sufficiently large for Arabic dots/diacritics.  The CSS
  // constrains the *display* size; this canvas is also the OCR source.
  const scale = Math.min(1, 2400 / Math.max(img.width, img.height));
  preview.width = Math.round(img.width * scale);
  preview.height = Math.round(img.height * scale);
  ctx.drawImage(img, 0, 0, preview.width, preview.height);
  showPreview();
  els.status.textContent = 'Analysing…';
  setTimeout(() => { analyse(); els.type.textContent = 'Arabic document image'; }, 250);
}

async function renderPdfPage(pageNumber) {
  const token = ++renderToken;
  els.status.textContent = 'Rendering PDF…';
  const page = await pdfDocument.getPage(pageNumber);
  if (token !== renderToken) return;
  const base = page.getViewport({ scale: 1 });
  const viewport = page.getViewport({ scale: Math.min(2400 / Math.max(base.width, base.height), 3) });
  preview.width = Math.round(viewport.width);
  preview.height = Math.round(viewport.height);
  await page.render({ canvasContext: ctx, viewport }).promise;
  if (token !== renderToken) return;
  currentPage = pageNumber;
  showPreview(); updatePdfControls(); analyse();
  els.type.textContent = `PDF document · page ${currentPage} of ${pdfDocument.numPages}`;
}

async function loadPdf(file) {
  try {
    els.status.textContent = 'Opening PDF…';
    pdfDocument = await pdfjsLib.getDocument({ data: await file.arrayBuffer() }).promise;
    currentPage = 1; updatePdfControls();
    await renderPdfPage(1);
  } catch (error) {
    console.error(error); pdfDocument = null; updatePdfControls();
    els.status.textContent = 'Could not open PDF';
    alert('This PDF could not be opened. It may be encrypted or damaged.');
  }
}

function loadFile(file) {
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) { alert('Please choose a document smaller than 20 MB.'); return; }
  currentFilename = file.name.replace(/\.[^.]+$/, '') || 'arabic-document';
  if (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')) { loadPdf(file); return; }
  if (!file.type.startsWith('image/')) { alert('Please choose a PDF, JPG, PNG, or WebP file.'); return; }
  pdfDocument = null; updatePdfControls();
  const img = new Image();
  img.onload = () => { drawImage(img); URL.revokeObjectURL(img.src); };
  img.onerror = () => { URL.revokeObjectURL(img.src); alert('This image could not be opened.'); };
  img.src = URL.createObjectURL(file);
}

async function getOcrWorker() {
  if (ocrWorker) return ocrWorker;
  ocrWorker = await Tesseract.createWorker('ara', 1, {
    logger(message) {
      const progress = Math.round((message.progress || 0) * 100);
      ocrProgress.textContent = message.status ? message.status.replace(/_/g, ' ') : 'Preparing OCR';
      ocrProgressBar.value = progress;
    }
  });
  return ocrWorker;
}

function makeOcrCanvas() {
  // OCR needs a clean, enlarged copy, while the preview must retain its
  // original colours.  Avoid hard thresholding: it commonly removes Arabic
  // dots and makes coloured identity cards worse.
  const longestSide = Math.max(preview.width, preview.height);
  const scale = Math.min(2, 2800 / longestSide);
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(preview.width * scale);
  canvas.height = Math.round(preview.height * scale);
  const ocrCtx = canvas.getContext('2d', { willReadFrequently: true });
  ocrCtx.imageSmoothingEnabled = true;
  ocrCtx.imageSmoothingQuality = 'high';
  ocrCtx.filter = 'grayscale(1) contrast(1.65) brightness(1.08)';
  ocrCtx.drawImage(preview, 0, 0, canvas.width, canvas.height);
  ocrCtx.filter = 'none';
  return canvas;
}

function candidateScore(result) {
  const words = result.data.words || [];
  const wordConfidence = words.length
    ? words.reduce((total, word) => total + (word.confidence || 0), 0) / words.length
    : result.data.confidence || 0;
  // A tiny length component breaks ties in favour of a complete layout pass,
  // without allowing random noise to win over confidence.
  return wordConfidence + Math.min(8, (result.data.text || '').trim().length / 45);
}

async function runOcr() {
  runOcrButton.disabled = true;
  ocrProgress.textContent = 'Loading Arabic OCR…'; ocrProgressBar.value = 0; ocrConfidence.textContent = '—';
  try {
    const worker = await getOcrWorker();
    const ocrCanvas = makeOcrCanvas();
    ocrProgress.textContent = 'Enhancing image for Arabic text…';
    ocrProgressBar.value = 18;

    // Sparse text mode is substantially better for IDs, certificates and
    // mixed image/text cards than Tesseract's default newspaper-page layout.
    await worker.setParameters({ tessedit_pageseg_mode: '11', preserve_interword_spaces: '1' });
    const sparseResult = await worker.recognize(ocrCanvas);
    ocrProgress.textContent = 'Checking Arabic text layout…';
    ocrProgressBar.value = 78;
    await worker.setParameters({ tessedit_pageseg_mode: '6', preserve_interword_spaces: '1' });
    const blockResult = await worker.recognize(ocrCanvas);
    const result = candidateScore(sparseResult) >= candidateScore(blockResult) ? sparseResult : blockResult;
    const text = result.data.text.trim();
    const confidence = Math.round(result.data.confidence || 0);
    lastOcrResult = {
      filename: currentFilename,
      page: pdfDocument ? currentPage : 1,
      pageCount: pdfDocument ? pdfDocument.numPages : 1,
      language: 'ara', confidence, text,
      qualityScore: Number(els.score.textContent) || null,
      createdAt: new Date().toISOString()
    };
    setOutput(text || 'لم يتم العثور على نص عربي واضح في هذه الصفحة.');
    ocrProgress.textContent = text ? 'Extraction complete' : 'No clear text found';
    ocrProgressBar.value = 100; ocrConfidence.textContent = `${confidence}%`;
    downloadTextButton.disabled = !text; downloadJsonButton.disabled = !text;
  } catch (error) {
    console.error(error);
    ocrProgress.textContent = 'OCR failed'; ocrProgressBar.value = 0;
    setOutput('تعذّر استخراج النص. تحقق من الاتصال وحاول مرة أخرى بصورة أوضح.');
  } finally {
    runOcrButton.disabled = false;
  }
}

function download(content, extension, type) {
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([content], { type }));
  link.download = `${currentFilename}-page-${pdfDocument ? currentPage : 1}.${extension}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

fileInput.addEventListener('change', event => loadFile(event.target.files[0]));
const drop = document.querySelector('#dropzone');
drop.addEventListener('dragover', event => { event.preventDefault(); drop.style.borderColor = '#174f3b'; });
drop.addEventListener('dragleave', () => { drop.style.borderColor = ''; });
drop.addEventListener('drop', event => { event.preventDefault(); drop.style.borderColor = ''; loadFile(event.dataTransfer.files[0]); });

document.querySelector('#sampleButton').addEventListener('click', () => {
  pdfDocument = null; updatePdfControls();
  preview.width = 720; preview.height = 900; ctx.fillStyle = '#e9dfc8'; ctx.fillRect(0, 0, 720, 900);
  ctx.strokeStyle = 'rgba(75,54,28,.22)'; ctx.lineWidth = 2; ctx.strokeRect(46, 42, 628, 816);
  ctx.fillStyle = '#55452f'; ctx.textAlign = 'right'; ctx.font = 'bold 42px serif';
  ctx.fillText('العلم نور يضيء طريق المستقبل', 640, 170); ctx.font = '28px serif';
  ['نحفظ تراثنا العربي ونمنحه حياة جديدة', 'من خلال أدوات رقمية مسؤولة ودقيقة', 'لتبقى المعرفة متاحة للأجيال القادمة', 'وتصل من الماضي إلى المستقبل'].forEach((text, i) => ctx.fillText(text, 640, 280 + i * 72));
  ctx.strokeStyle = 'rgba(92,62,25,.12)';
  for (let i = 0; i < 11; i++) { ctx.beginPath(); ctx.moveTo(80, 220 + i * 58); ctx.lineTo(640, 220 + i * 58); ctx.stroke(); }
  showPreview(); els.status.textContent = 'Analysing…';
  currentFilename = 'turath-heritage-sample';
  setTimeout(() => { analyse(); setOutput('العلم نور يضيء طريق المستقبل. نحفظ تراثنا العربي ونمنحه حياة جديدة من خلال أدوات رقمية مسؤولة ودقيقة.'); els.type.textContent = 'Heritage manuscript sample'; }, 250);
});

runOcrButton.addEventListener('click', runOcr);
downloadTextButton.addEventListener('click', () => { if (lastOcrResult) download(els.text.value, 'txt', 'text/plain;charset=utf-8'); });
downloadJsonButton.addEventListener('click', () => { if (lastOcrResult) download(JSON.stringify({ ...lastOcrResult, text: els.text.value }, null, 2), 'json', 'application/json'); });
previousPage.addEventListener('click', () => { if (pdfDocument && currentPage > 1) renderPdfPage(currentPage - 1); });
nextPage.addEventListener('click', () => { if (pdfDocument && currentPage < pdfDocument.numPages) renderPdfPage(currentPage + 1); });
document.querySelector('#clearButton').addEventListener('click', () => {
  renderToken++; pdfDocument = null; currentPage = 1; updatePdfControls(); preview.style.display = 'none'; prompt.style.display = 'flex'; fileInput.value = '';
  els.score.textContent = '—'; els.ring.style.strokeDasharray = '0 100';
  ['brightness', 'contrast', 'sharpness'].forEach(name => { els[name].textContent = '—'; document.querySelector(`#${name}Bar`).style.width = '0'; });
  runOcrButton.disabled = true; resetOcrResult();
  els.status.textContent = 'Ready'; setOutput('حمّل مستنداً أو استخدم العينة لبدء التحليل.'); els.type.textContent = 'Not analysed';
});

document.querySelectorAll('.tabs button').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.tabs button,.tab-content').forEach(item => item.classList.remove('active'));
  button.classList.add('active'); document.querySelector(button.dataset.tab === 'text' ? '#textTab' : '#metadataTab').classList.add('active');
}));
