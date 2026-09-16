const ssblFileInput = document.getElementById('ssblFile');
const applicationFileInput = document.getElementById('applicationFile');
const ssblFileName = document.getElementById('ssblFileName');
const applicationFileName = document.getElementById('applicationFileName');
const flashButton = document.getElementById('flashButton');
const statusText = document.getElementById('statusText');
const progressFill = document.getElementById('progressFill');
const progressPercent = document.getElementById('progressPercent');
const errorBox = document.getElementById('errorBox');
const summary = document.getElementById('summary');

const ssblSource = document.getElementById('ssblSourceAddress');
const ssblDestination = document.getElementById('ssblDestinationAddress');
const appSource = document.getElementById('applicationSourceAddress');
const appDestination = document.getElementById('applicationDestinationAddress');

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove('hidden');
}

function clearError() {
  errorBox.textContent = '';
  errorBox.classList.add('hidden');
}

function updateSummary() {
  const ssblPath = ssblFileInput.files[0] ? ssblFileInput.files[0].name : 'None';
  const appPath = applicationFileInput.files[0] ? applicationFileInput.files[0].name : 'None';

  summary.innerHTML = `
    <p><strong>SSBL:</strong></p>
    <p>File: ${ssblPath}</p>
    <p>Source: ${ssblSource.value || '0x08000000'}</p>
    <p>Destination: ${ssblDestination.value || '0x08000000'}</p>
    <p><strong>Application:</strong></p>
    <p>File: ${appPath}</p>
    <p>Source: ${appSource.value || '0x08010000'}</p>
    <p>Destination: ${appDestination.value || '0x08010000'}</p>
  `;
}

function setStatus(message, percent = 0) {
  statusText.textContent = message;
  progressFill.style.width = `${percent}%`;
  progressPercent.textContent = `${percent}%`;
}

function validateHexAddress(value, label) {
  const pattern = /^(0x)?[0-9A-Fa-f]+$/;
  if (!value || !pattern.test(value)) {
    return `Invalid ${label}. Enter a hexadecimal address such as 0x08000000.`;
  }

  try {
    const address = parseInt(value, 16);
    if (Number.isNaN(address) || address < 0 || address < 0x08000000 || address > 0x0fffffff) {
      return `Invalid ${label}. Address is outside the supported MCU flash range.`;
    }
    return '';
  } catch (error) {
    return `Invalid ${label}. Enter a hexadecimal address such as 0x08000000.`;
  }
}

function validateForm() {
  if (!ssblFileInput.files[0]) {
    return 'Please select an SSBL file.';
  }

  if (!applicationFileInput.files[0]) {
    return 'Please select an application file.';
  }

  const ssblSourceError = validateHexAddress(ssblSource.value, 'SSBL source address');
  if (ssblSourceError) return ssblSourceError;

  const ssblDestinationError = validateHexAddress(ssblDestination.value, 'SSBL destination address');
  if (ssblDestinationError) return ssblDestinationError;

  const appSourceError = validateHexAddress(appSource.value, 'Application source address');
  if (appSourceError) return appSourceError;

  const appDestinationError = validateHexAddress(appDestination.value, 'Application destination address');
  if (appDestinationError) return appDestinationError;

  return '';
}

function updateFileDisplay() {
  ssblFileName.textContent = ssblFileInput.files[0] ? ssblFileInput.files[0].name : 'No file selected';
  applicationFileName.textContent = applicationFileInput.files[0] ? applicationFileInput.files[0].name : 'No file selected';
  updateSummary();
}

ssblFileInput.addEventListener('change', updateFileDisplay);
applicationFileInput.addEventListener('change', updateFileDisplay);
[ssblSource, ssblDestination, appSource, appDestination].forEach((input) => input.addEventListener('input', updateSummary));

flashButton.addEventListener('click', async () => {
  clearError();
  const validationError = validateForm();
  if (validationError) {
    showError(validationError);
    return;
  }

  flashButton.disabled = true;
  flashButton.textContent = 'FLASHING...';
  setStatus('Preparing flash...', 5);

  const formData = new FormData();
  formData.append('ssbl_file', ssblFileInput.files[0]);
  formData.append('application_file', applicationFileInput.files[0]);
  formData.append('ssbl_source_address', ssblSource.value.trim());
  formData.append('ssbl_destination_address', ssblDestination.value.trim());
  formData.append('application_source_address', appSource.value.trim());
  formData.append('application_destination_address', appDestination.value.trim());

  try {
    setStatus('Flashing SSBL...', 25);
    await new Promise((resolve) => setTimeout(resolve, 500));

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
      throw new Error(payload.error || 'Flash failed.');
    }

    setStatus('SSBL flash completed', 50);
    await new Promise((resolve) => setTimeout(resolve, 400));
    setStatus('Flashing Application...', 75);
    await new Promise((resolve) => setTimeout(resolve, 500));
    setStatus('Application flash completed', 90);
    await new Promise((resolve) => setTimeout(resolve, 300));
    setStatus('Flash completed successfully', 100);
  } catch (error) {
    setStatus(`Flash failed: ${error.message}`, 0);
    showError(`Flash failed. Reason: ${error.message}`);
  } finally {
    flashButton.disabled = false;
    flashButton.textContent = 'FLASH';
  }
});

updateSummary();
