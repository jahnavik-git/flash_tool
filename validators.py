import os
import re
from typing import IO

HEX_ADDRESS_PATTERN = re.compile(r"^0x[0-9A-Fa-f]+$", re.IGNORECASE)
ALLOWED_EXTENSIONS = {"bin", "hex", "out"}
INVALID_FIRMWARE_MESSAGE = "Invalid file uploaded. Only .bin, .hex, and .out firmware files are allowed."
MAX_UPLOAD_SIZE = 16 * 1024 * 1024

MIN_ADDRESS = 0x0000
MAX_ADDRESS = 0x0FFF
INVALID_HEX_ADDRESS_MESSAGE = "Invalid hexadecimal address."
ADDRESS_RANGE_MESSAGE = "Address must be within the 4 KB range (0x0000 - 0x0FFF)."


def validate_hex_address(value: str, field_name: str) -> int:
    if value is None:
        raise ValueError(f"{field_name}: {INVALID_HEX_ADDRESS_MESSAGE}")

    value = str(value).strip()
    if not value or not HEX_ADDRESS_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name}: {INVALID_HEX_ADDRESS_MESSAGE}")

    try:
        address = int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{field_name}: {INVALID_HEX_ADDRESS_MESSAGE}") from exc

    if address < MIN_ADDRESS or address > MAX_ADDRESS:
        raise ValueError(f"{field_name}: {ADDRESS_RANGE_MESSAGE}")

    return address


def validate_file_upload(file: IO, field_name: str, max_size_bytes: int = MAX_UPLOAD_SIZE) -> str:
    if file is None:
        raise ValueError(f"Please select a {field_name} file.")

    filename = file.filename or ""
    if not filename:
        raise ValueError(f"Please select a {field_name} file.")

    ext = os.path.splitext(filename)[1][1:].lower() if os.path.splitext(filename)[1] else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(INVALID_FIRMWARE_MESSAGE)

    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size == 0:
        raise ValueError(f"The {field_name} file is empty.")

    if file_size > max_size_bytes:
        raise ValueError(f"The {field_name} file exceeds the maximum upload size of {max_size_bytes / (1024 * 1024):.0f} MB.")

    return filename
