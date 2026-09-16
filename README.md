# Azimuth Flash Utility

Azimuth Flash Utility is a Flask-based firmware flashing interface for embedded developers who want to review SSBL and application memory configuration before flashing.

The initial implementation runs in Simulation Mode so it can be tested safely without a hardware programmer. The design keeps the actual flashing backend replaceable through a `FlashProgrammer` interface so it can later be connected to STM32, J-Link, ST-LINK, OpenOCD, or another command-line flasher.

## Project Purpose

- Configure SSBL and application firmware files
- Enter source and destination flash addresses in hexadecimal format
- Validate file and address inputs before sending the request to the backend
- Simulate the full flash workflow safely in a non-invasive mode
- Prepare the application for real hardware programming later with a replaceable flashing backend

## Requirements

- Python 3.10+
- Flask

## Python Installation

On Windows:

```powershell
python -m venv venv
venv\Scripts\activate
```

On macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

## Installing Dependencies

```bash
pip install -r requirements.txt
```

## Running Flask

```bash
python app.py
```

The application will start on a local Flask URL such as:

```text
http://127.0.0.1:5000/
```

Open this URL in the browser to use the utility.

## Configuration

The web interface allows the user to enter:

- SSBL file path
- SSBL source address
- SSBL destination address
- Application file path
- Application source address
- Application destination address

Accepted firmware file extensions are:

- .bin
- .hex
- .elf

Addresses should be entered in hexadecimal form such as:

```text
0x08000000
0x08010000
```

## Simulation Mode

This project starts in Simulation Mode by default. It does not interact with hardware and does not modify physical devices.

The simulation is intentionally clear and safe, with the backend returning a status that states:

```text
Simulation Mode
```

This makes it suitable for development, UI validation, and workflow demonstration without connected hardware.

## Connecting a Real Programmer

To connect a real flashing mechanism, replace the default `SimulationFlashProgrammer` in `flash_service.py` or plug a custom programmer implementation into `FlashProgrammer`.

Example architecture:

```python
class FlashProgrammer:
    def flash(self, file_path, source_address, destination_address):
        pass
```

You can then implement a real driver for:

- STM32 programmer
- J-Link
- ST-LINK
- OpenOCD
- other command-line flashing tools

The `flash_firmware` function is intentionally kept separate from the Flask routes so the real programmer can be swapped in without changing the API layer.

## Flashing Workflow

1. Select SSBL file
2. Enter SSBL source address
3. Enter SSBL destination address
4. Select application file
5. Enter application source address
6. Enter application destination address
7. Review the configuration summary
8. Click FLASH
9. Monitor progress and status updates
10. Receive success or failure notification

## Troubleshooting

### File is rejected

Check the extension and confirm the file is not empty.

### Invalid address

Use hexadecimal values like:

```text
0x08000000
0x08010000
```

### Flash request fails

Check the browser console and the Flask terminal output for the actual backend error message.

### No hardware is connected

This implementation is intentionally in Simulation Mode and will not flash hardware unless a real programmer is configured.

## Security Notes

- Uploaded firmware files are treated as data only
- No uploaded file is executed
- Upload size is limited
- Filenames are sanitized with `secure_filename`
- The project uses validation for both file type and address range

## Example API Request

The backend exposes this endpoint:

```text
POST /api/flash
```

The request uses multipart form data with the following fields:

- ssbl_file
- application_file
- ssbl_source_address
- ssbl_destination_address
- application_source_address
- application_destination_address
