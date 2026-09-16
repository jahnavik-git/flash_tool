import os
import re
from typing import IO

HEX_ADDRESS_PATTERN = re.compile(r"^(?:0x)?[0-9A-Fa-f]+$")
ALLOWED_EXTENSIONS = {".bin", ".hex", ".elf"}
MAX_UPLOAD_SIZE = 16 * 1024 * 1024


def validate_hex_address(value: str, field_name: str) -> int:
    if value is None:
        raise ValueError(f"Invalid {field_name}. Enter a hexadecimal address such as 0x08000000.")

    value = str(value).strip()
    if not value or not HEX_ADDRESS_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid {field_name}. Enter a hexadecimal address such as 0x08000000.")

    try:
        address = int(value, 16)
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}. Enter a hexadecimal address such as 0x08000000.") from exc

    if address < 0:
        raise ValueError(f"Invalid {field_name}. Value must be non-negative.")

    # Typical MCU flash range for embedded firmware images.
    if address < 0x08000000 or address > 0x0FFFFFFF:
        raise ValueError(f"Invalid {field_name}. Address is outside the supported MCU flash range.")

    return address


def validate_file_upload(file: IO, field_name: str, max_size_bytes: int = MAX_UPLOAD_SIZE) -> str:
    if file is None:
        raise ValueError(f"Please select a {field_name} file.")

    filename = file.filename or ""
    if not filename:
        raise ValueError(f"Please select a {field_name} file.")

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported {field_name} file type. Allowed types: .bin, .hex, .elf.")

    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size == 0:
        raise ValueError(f"The {field_name} file is empty.")

    if file_size > max_size_bytes:
        raise ValueError(f"The {field_name} file exceeds the maximum upload size of {max_size_bytes / (1024 * 1024):.0f} MB.")

    return filename
