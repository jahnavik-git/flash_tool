const flashButton = document.getElementById('flashButton');
const errorBox = document.getElementById('errorBox');
const summary = document.getElementById('summary');

const flashProgressBar = document.getElementById('flashProgressBar');
const flashProgressFill = document.getElementById('flashProgressFill');
const flashProgressTextBase = document.getElementById('flashProgressTextBase');
const flashProgressTextFill = document.getElementById('flashProgressTextFill');
const flashTotalTime = document.getElementById('flashTotalTime');

const FIRMWARE_UNITS = [
  { prefix: 'core0Ssbl', formPrefix: 'core0_ssbl', label: 'Core 0 SSBL' },
  { prefix: 'core0Application', formPrefix: 'core0_application', label: 'Core 0 Application' },
  { prefix: 'core1Application', formPrefix: 'core1_application', label: 'Core 1 Application' },
];

function getUnitElements(unit) {
  return {
    source: document.getElementById(`${unit.prefix}SourceAddress`),
    destination: document.getElementById(`${unit.prefix}DestinationAddress`),
    sourceError: document.getElementById(`${unit.prefix}SourceError`),
    destinationError: document.getElementById(`${unit.prefix}DestinationError`),
    fileInput: document.getElementById(`${unit.prefix}File`),
    filePath: document.getElementById(`${unit.prefix}FilePath`),
    fileWrap: document.getElementById(`${unit.prefix}FileWrap`),
    fileError: document.getElementById(`${unit.prefix}FileError`),
  };
}

const UNIT_ELEMENTS = FIRMWARE_UNITS.map((unit) => ({ unit, els: getUnitElements(unit) }));

const SUPPORTED_FIRMWARE_EXTENSIONS = ['bin', 'hex', 'out'];
const INVALID_FIRMWARE_MESSAGE = 'Invalid file uploaded. Only .bin, .hex, and .out firmware files are allowed.';
const VALID_FIRMWARE_MESSAGE = 'Valid file accepted (.bin, .hex, .out).';

const RECENT_ADDRESSES_KEY = 'azimuth_flash_recent_addresses';
const MAX_RECENT_ADDRESSES = 8;

const MIN_ADDRESS_VALUE = 0x0000;
const MAX_ADDRESS_VALUE = 0x0FFF;
const HEX_ADDRESS_PATTERN = /^0x[0-9A-Fa-f]+$/i;
const INVALID_HEX_ADDRESS_MESSAGE = 'Invalid hexadecimal address.';
const ADDRESS_RANGE_MESSAGE = 'Address must be within the 4 KB range (0x0000 - 0x0FFF).';
const ADDRESS_ORDER_MESSAGE = 'Ending Address must be greater than or equal to Starting Address.';

function showError(message) {
  if (!errorBox) {
    return;
  }
  errorBox.textContent = message;
  errorBox.classList.remove('hidden');
}

function clearError() {
  if (!errorBox) {
    return;
  }
  errorBox.textContent = '';
  errorBox.classList.add('hidden');
}

function getRecentAddresses() {
  try {
    const stored = JSON.parse(localStorage.getItem(RECENT_ADDRESSES_KEY) || '[]');
    if (!Array.isArray(stored)) {
      return [];
    }

    const unique = [];
    const seen = new Set();

    stored.forEach((value) => {
      if (typeof value !== 'string') {
        return;
      }
      const trimmed = value.trim();
      if (!trimmed || !HEX_ADDRESS_PATTERN.test(trimmed) || seen.has(trimmed.toLowerCase())) {
        return;
      }
      seen.add(trimmed.toLowerCase());
      unique.push(trimmed);
    });

    return unique;
  } catch (error) {
    return [];
  }
}

function saveRecentAddress(value) {
  const trimmed = (value || '').trim();
  if (!trimmed || !HEX_ADDRESS_PATTERN.test(trimmed)) {
    return;
  }

  const existing = getRecentAddresses().filter((item) => item.toLowerCase() !== trimmed.toLowerCase());
  const next = [trimmed, ...existing].slice(0, MAX_RECENT_ADDRESSES);
  localStorage.setItem(RECENT_ADDRESSES_KEY, JSON.stringify(next));
}

function getFilteredRecentAddresses(inputValue) {
  const query = (inputValue || '').trim().toLowerCase();
  const recent = getRecentAddresses();

  if (!query) {
    return recent;
  }

  return recent.filter((value) => value.toLowerCase().includes(query));
}

function updateRecentAddressSuggestions(els, isEnding) {
  const input = isEnding ? els.destination : els.source;
  const field = input && input.closest('.compact-field');
  if (!field) {
    return;
  }

  let panel = field.querySelector('.recent-address-panel');
  if (!panel) {
    panel = document.createElement('div');
    panel.className = 'recent-address-panel hidden';
    field.appendChild(panel);
  }

  const matches = getFilteredRecentAddresses(input.value);
  if (!matches.length) {
    panel.classList.add('hidden');
    panel.innerHTML = '';
    return;
  }

  panel.innerHTML = `
    <div class="recent-address-header">RECENT ADDRESSES</div>
    <div class="recent-address-list">
      ${matches.map((value) => `
        <div class="recent-address-item">
          <button type="button" class="recent-address-select" data-value="${value}">${value}</button>
        </div>
      `).join('')}
    </div>
  `;

  panel.classList.remove('hidden');

  panel.querySelectorAll('.recent-address-select').forEach((button) => {
    button.addEventListener('mousedown', (event) => {
      event.preventDefault();
    });

    button.addEventListener('click', () => {
      input.value = button.dataset.value || '';
      panel.classList.add('hidden');
      validateAddressPair(els);
      updateSummary();
      input.focus();
    });
  });
}

function updateSummary() {
  if (!summary) {
    return;
  }

  const blocks = UNIT_ELEMENTS.map(({ unit, els }) => {
    const fileName = els.fileInput && els.fileInput.files[0] ? els.fileInput.files[0].name : 'None';
    return `
      <p><strong>${unit.label}:</strong></p>
      <p>File: ${fileName}</p>
      <p>Source: ${els.source ? els.source.value || '' : ''}</p>
      <p>Destination: ${els.destination ? els.destination.value || '' : ''}</p>
    `;
  });

  summary.innerHTML = blocks.join('');
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const FLASH_SWAP_TRANSITION_MS = 250;

function crossFadeSwap(hideEl, showEl) {
  if (!hideEl || !showEl) {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    hideEl.classList.add('flash-fade-out');

    setTimeout(() => {
      hideEl.classList.add('hidden');
      hideEl.classList.remove('flash-fade-out');

      showEl.classList.remove('hidden');
      showEl.classList.add('flash-fade-in-start');
      void showEl.offsetWidth;
      showEl.classList.remove('flash-fade-in-start');

      setTimeout(resolve, FLASH_SWAP_TRANSITION_MS);
    }, FLASH_SWAP_TRANSITION_MS);
  });
}

function setFlashProgress(label, percent) {
  if (!flashProgressBar) {
    return;
  }
  const clamped = Math.max(0, Math.min(100, Math.round(percent)));
  const text = `${label} ${clamped}%`;
  flashProgressFill.style.width = `${clamped}%`;
  flashProgressTextBase.textContent = text;
  flashProgressTextFill.textContent = text;
  flashProgressTextFill.style.width = `${flashProgressBar.clientWidth}px`;
  flashProgressBar.setAttribute('aria-valuenow', String(clamped));
}

function showFlashProgress() {
  if (!flashProgressBar) {
    return Promise.resolve();
  }
  flashProgressBar.classList.remove('flash-progress-failed');
  return crossFadeSwap(flashButton, flashProgressBar);
}

function hideFlashProgress() {
  if (!flashProgressBar) {
    return Promise.resolve();
  }
  return crossFadeSwap(flashProgressBar, flashButton);
}

function setFlashFailed(percent) {
  if (!flashProgressBar) {
    return;
  }
  const clamped = Math.max(0, Math.min(100, Math.round(percent)));
  const text = `Flash failed ${clamped}%`;
  flashProgressBar.classList.add('flash-progress-failed');
  flashProgressTextBase.textContent = text;
  flashProgressTextFill.textContent = text;
  flashProgressTextFill.style.width = `${flashProgressBar.clientWidth}px`;
}

function formatElapsedTime(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (value) => String(value).padStart(2, '0');

  if (hours > 0) {
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  }
  return `${pad(minutes)}:${pad(seconds)}`;
}

let flashTimerInterval = null;

function clearTotalTime() {
  if (!flashTotalTime) {
    return;
  }
  flashTotalTime.textContent = '';
  flashTotalTime.classList.add('hidden');
  flashTotalTime.classList.remove('flash-total-time-failed');
}

function startLiveTimer(startTime) {
  if (!flashTotalTime) {
    return;
  }
  stopLiveTimer();
  flashTotalTime.classList.remove('flash-total-time-failed');
  flashTotalTime.classList.remove('hidden');
  flashTotalTime.textContent = `Total Time: ${formatElapsedTime(0)}`;
  flashTimerInterval = setInterval(() => {
    flashTotalTime.textContent = `Total Time: ${formatElapsedTime(Date.now() - startTime)}`;
  }, 250);
}

function stopLiveTimer() {
  if (flashTimerInterval !== null) {
    clearInterval(flashTimerInterval);
    flashTimerInterval = null;
  }
}

function showTotalTime(elapsedMs, failed) {
  if (!flashTotalTime) {
    return;
  }
  stopLiveTimer();
  const formatted = formatElapsedTime(elapsedMs);
  flashTotalTime.textContent = failed ? `Failed — Total Time: ${formatted}` : `Total Time: ${formatted}`;
  flashTotalTime.classList.toggle('flash-total-time-failed', Boolean(failed));
  flashTotalTime.classList.remove('hidden');
}

function updatePageScrollState() {
  const hasValidationErrors = [...document.querySelectorAll('.error-message')].some((element) => element.textContent.trim().length > 0);
  document.body.classList.toggle('validation-errors', hasValidationErrors);
}

function setFileError(wrapper, message, errorElement) {
  if (wrapper) {
    wrapper.classList.toggle('input-error', Boolean(message));
  }
  if (errorElement) {
    errorElement.textContent = message;
    errorElement.classList.remove('success-message');
  }
  updatePageScrollState();
}

function setFileSuccess(wrapper, message, errorElement) {
  if (wrapper) {
    wrapper.classList.remove('input-error');
  }
  if (errorElement) {
    errorElement.textContent = message;
    errorElement.classList.add('success-message');
  }
  updatePageScrollState();
}

function validateAddress(value, isEnding) {
  const trimmed = (value || '').trim();
  if (!trimmed) {
    return isEnding ? 'Ending Address is required' : 'Starting Address is required';
  }
  if (!HEX_ADDRESS_PATTERN.test(trimmed)) {
    return INVALID_HEX_ADDRESS_MESSAGE;
  }
  const numericValue = parseInt(trimmed.replace(/^0x/i, ''), 16);
  if (numericValue < MIN_ADDRESS_VALUE || numericValue > MAX_ADDRESS_VALUE) {
    return ADDRESS_RANGE_MESSAGE;
  }
  return '';
}

function getFileExtension(fileName) {
  if (!fileName) {
    return '';
  }

  const extension = fileName.includes('.') ? fileName.slice(fileName.lastIndexOf('.') + 1) : '';
  return extension.toLowerCase();
}

function isValidFirmwareFile(fileName) {
  return SUPPORTED_FIRMWARE_EXTENSIONS.includes(getFileExtension(fileName));
}

function validateFileSelection(fileInput, requiredText, errorElement, wrapper, pathDisplay) {
  if (!fileInput.files[0]) {
    setFileError(wrapper, requiredText, errorElement);
    return false;
  }

  const fileName = fileInput.files[0].name || '';
  if (!isValidFirmwareFile(fileName)) {
    fileInput.value = '';
    if (pathDisplay) {
      pathDisplay.value = '';
    }
    setFileError(wrapper, INVALID_FIRMWARE_MESSAGE, errorElement);
    updateSummary();
    return false;
  }

  setFileSuccess(wrapper, VALID_FIRMWARE_MESSAGE, errorElement);
  return true;
}

function validateAddressPair(els) {
  const sourceMessage = validateAddress(els.source.value, false);
  let destinationMessage = validateAddress(els.destination.value, true);

  if (!sourceMessage && !destinationMessage) {
    const sourceValue = parseInt(els.source.value.trim().replace(/^0x/i, ''), 16);
    const destinationValue = parseInt(els.destination.value.trim().replace(/^0x/i, ''), 16);
    if (sourceValue > destinationValue) {
      destinationMessage = ADDRESS_ORDER_MESSAGE;
    }
  }

  els.source.classList.toggle('input-error', Boolean(sourceMessage));
  els.sourceError.textContent = sourceMessage;

  els.destination.classList.toggle('input-error', Boolean(destinationMessage));
  els.destinationError.textContent = destinationMessage;

  updatePageScrollState();
  return !sourceMessage && !destinationMessage;
}

function validateForm() {
  let isValid = true;

  UNIT_ELEMENTS.forEach(({ unit, els }) => {
    if (!validateAddressPair(els)) {
      isValid = false;
    }
    if (!validateFileSelection(els.fileInput, `${unit.label} file is required`, els.fileError, els.fileWrap, els.filePath)) {
      isValid = false;
    }
  });

  return isValid;
}

function updateFileDisplay(els) {
  const file = els.fileInput.files && els.fileInput.files[0];
  const fileName = file ? (file.name || '') : '';

  if (!fileName) {
    els.filePath.value = '';
    setFileError(els.fileWrap, '', els.fileError);
    updatePageScrollState();
    updateSummary();
    return;
  }

  if (!isValidFirmwareFile(fileName)) {
    els.fileInput.value = '';
    els.filePath.value = '';
    setFileError(els.fileWrap, INVALID_FIRMWARE_MESSAGE, els.fileError);
    updatePageScrollState();
    updateSummary();
    return;
  }

  els.filePath.value = fileName;
  setFileSuccess(els.fileWrap, VALID_FIRMWARE_MESSAGE, els.fileError);
  updatePageScrollState();
  updateSummary();
}

function triggerFileInput(fileInputId) {
  const fileInput = document.getElementById(fileInputId);
  if (fileInput) {
    fileInput.click();
  }
}

function openSelectedFile(fileInputId) {
  const fileInput = document.getElementById(fileInputId);
  if (!fileInput || !fileInput.files || !fileInput.files[0]) {
    triggerFileInput(fileInputId);
    return;
  }

  const file = fileInput.files[0];
  const fileUrl = URL.createObjectURL(file);
  window.open(fileUrl, '_blank');
}

function bindAddressInput(els, isEnding) {
  const input = isEnding ? els.destination : els.source;
  const errorElement = isEnding ? els.destinationError : els.sourceError;
  if (!input) {
    return;
  }

  input.setAttribute('autocomplete', 'off');

  input.addEventListener('focus', () => {
    updateRecentAddressSuggestions(els, isEnding);
  });

  input.addEventListener('click', () => {
    updateRecentAddressSuggestions(els, isEnding);
  });

  input.addEventListener('input', () => {
    validateAddressPair(els);
    updateSummary();
    updateRecentAddressSuggestions(els, isEnding);
  });

  input.addEventListener('blur', () => {
    setTimeout(() => {
      const panel = input.closest('.compact-field')?.querySelector('.recent-address-panel');
      if (panel) {
        panel.classList.add('hidden');
      }
    }, 120);

    const trimmed = input.value.trim();
    if (trimmed && !errorElement.textContent) {
      saveRecentAddress(trimmed);
    }
  });
}

UNIT_ELEMENTS.forEach(({ els }) => {
  bindAddressInput(els, false);
  bindAddressInput(els, true);

  els.fileInput.addEventListener('change', () => updateFileDisplay(els));
});

document.querySelectorAll('.path-button[data-file-input]').forEach((button) => {
  button.addEventListener('click', () => {
    const targetId = button.dataset.fileInput;
    const targetInput = document.getElementById(targetId);
    if (targetInput) {
      triggerFileInput(targetId);
    }
  });
});

document.querySelectorAll('.path-view-button[data-view-file]').forEach((button) => {
  button.addEventListener('click', () => {
    openSelectedFile(button.dataset.viewFile);
  });
});

UNIT_ELEMENTS.forEach(({ els }) => {
  if (!els.filePath) {
    return;
  }

  els.filePath.addEventListener('click', () => {
    if (els.fileInput && els.fileInput.files && els.fileInput.files[0]) {
      openSelectedFile(els.fileInput.id);
      return;
    }
    triggerFileInput(els.fileInput.id);
  });
});

flashButton.addEventListener('click', async () => {
  clearError();
  const isValid = validateForm();
  if (!isValid) {
    return;
  }

  flashButton.disabled = true;
  clearTotalTime();
  const flashStartTime = Date.now();
  await showFlashProgress();
  startLiveTimer(flashStartTime);
  setFlashProgress('Preparing', 0);

  const formData = new FormData();
  UNIT_ELEMENTS.forEach(({ unit, els }) => {
    formData.append(`${unit.formPrefix}_file`, els.fileInput.files[0]);
    formData.append(`${unit.formPrefix}_source_address`, els.source.value.trim());
    formData.append(`${unit.formPrefix}_destination_address`, els.destination.value.trim());
  });

  try {
    const response = await fetch('/api/flash', {
      method: 'POST',
      body: formData,
    });

    const contentType = response.headers.get('content-type') || '';
    let payload = null;
    if (contentType.includes('application/json')) {
      payload = await response.json();
    } else {
      payload = { success: false, error: await response.text() };
    }

    if (!response.ok || !payload.success) {
      setFlashProgress(payload.stage || 'Preparing', payload.percent || 0);
      const backendError = payload && payload.error ? payload.error : 'Flash failed.';
      throw new Error(backendError);
    }

    setFlashProgress(payload.stage || 'Completed', payload.percent || 100);

    const elapsedMs = Date.now() - flashStartTime;
    showTotalTime(elapsedMs, false);
    await hideFlashProgress();
  } catch (error) {
    const elapsedMs = Date.now() - flashStartTime;
    showTotalTime(elapsedMs, true);
    const currentPercent = Number(flashProgressBar.getAttribute('aria-valuenow')) || 0;
    setFlashFailed(currentPercent);
    showError(`Flash failed. Reason: ${error.message}`);
    await wait(1800);
    await hideFlashProgress();
  } finally {
    flashButton.disabled = false;
  }
});

// --- Core 0 SSBL CRC calculation ---
// Deliberately independent of the FLASH button/handler above: its own
// button, its own endpoint (/api/calculate-crc), its own state. It must
// never trigger flashing and flashing must never trigger it.

function buildCrcResultNode({ startAddress, endAddress, crcHex, outputFilename }, onOpenOutput) {
  const container = document.createElement('div');

  const addRow = (label, valueNode) => {
    const row = document.createElement('div');
    row.className = 'crc-result-line';
    const labelEl = document.createElement('span');
    labelEl.className = 'crc-result-label';
    labelEl.textContent = label;
    row.appendChild(labelEl);
    if (typeof valueNode === 'string') {
      row.appendChild(document.createTextNode(valueNode));
    } else {
      row.appendChild(valueNode);
    }
    container.appendChild(row);
  };

  const formatAddress = (value) => `0x${value.toString(16).toUpperCase().padStart(4, '0')}`;

  addRow('Start Address:', formatAddress(startAddress));
  addRow('End Address:', formatAddress(endAddress));
  addRow('CRC:', crcHex);

  const outputLink = document.createElement('button');
  outputLink.type = 'button';
  outputLink.className = 'crc-output-link';
  outputLink.textContent = outputFilename;
  outputLink.addEventListener('click', onOpenOutput);
  addRow('Output:', outputLink);

  return container;
}

(function initCore0SsblCrc() {
  const unitEntry = UNIT_ELEMENTS.find(({ unit }) => unit.prefix === 'core0Ssbl');
  const crcButton = document.getElementById('core0SsblCalculateCrcButton');
  const crcErrorEl = document.getElementById('core0SsblCrcError');
  const crcResultEl = document.getElementById('core0SsblCrcResult');

  if (!unitEntry || !crcButton || !crcErrorEl || !crcResultEl) {
    return;
  }

  const { els } = unitEntry;
  let outputBlobUrl = null;

  function clearCrcState() {
    crcErrorEl.textContent = '';
    crcResultEl.innerHTML = '';
    crcResultEl.classList.add('hidden');
    if (outputBlobUrl) {
      URL.revokeObjectURL(outputBlobUrl);
      outputBlobUrl = null;
    }
  }

  crcButton.addEventListener('click', async () => {
    clearCrcState();

    const addressValid = validateAddressPair(els);
    const fileValid = validateFileSelection(
      els.fileInput,
      'SSBL file is required',
      els.fileError,
      els.fileWrap,
      els.filePath
    );

    if (!addressValid || !fileValid) {
      return;
    }

    crcButton.disabled = true;

    try {
      const formData = new FormData();
      formData.append('file', els.fileInput.files[0]);
      formData.append('start_address', els.source.value.trim());
      formData.append('end_address', els.destination.value.trim());

      const response = await fetch('/api/calculate-crc', {
        method: 'POST',
        body: formData,
      });

      const contentType = response.headers.get('content-type') || '';
      const payload = contentType.includes('application/json')
        ? await response.json()
        : { success: false, error: await response.text() };

      if (!response.ok || !payload.success) {
        throw new Error(payload.error || 'CRC calculation failed.');
      }

      const binary = atob(payload.output_base64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: payload.output_content_type || 'application/octet-stream' });
      outputBlobUrl = URL.createObjectURL(blob);

      const resultNode = buildCrcResultNode(
        {
          startAddress: payload.start_address,
          endAddress: payload.end_address,
          crcHex: payload.crc_hex,
          outputFilename: payload.output_filename,
        },
        () => {
          const link = document.createElement('a');
          link.href = outputBlobUrl;
          link.download = payload.output_filename;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        }
      );

      crcResultEl.innerHTML = '';
      crcResultEl.appendChild(resultNode);
      crcResultEl.classList.remove('hidden');
    } catch (error) {
      crcErrorEl.textContent = error.message || 'CRC calculation failed.';
    } finally {
      crcButton.disabled = false;
    }
  });
})();

updateSummary();
