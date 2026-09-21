"""CRC calculation for the Azimuth Flash Utility (Core 0 SSBL only, for now).

No CRC algorithm, polynomial, or convention existed anywhere else in this
project, so the parameters below are defined explicitly here rather than
assumed. Every parameter is a named field on CrcAlgorithm so a different CRC
variant (for example the CRC-32/MPEG-2 flavor some hardware CRC peripherals
use, which is unreflected and has no final XOR) can be substituted later
without touching the calculation engine itself.

Default algorithm: CRC-32 (a.k.a. CRC-32/ISO-HDLC - the variant used by zip,
Ethernet, and PNG). Parameters, in the common "Rocksoft model" form:
    width  = 32
    poly   = 0x04C11DB7
    init   = 0xFFFFFFFF
    refin  = True   (each input byte is bit-reflected before use)
    refout = True   (the final register is bit-reflected before the XOR)
    xorout = 0xFFFFFFFF
    check  = 0xCBF43926  (the CRC of the ASCII bytes "123456789";
                          verified below as a self-test, not invented)

OUTPUT FILE CONVENTION: the generated "<name>_crc<ext>" file contains the
exact firmware bytes that were hashed (the requested address range) with the
computed CRC value appended as `width // 8` big-endian bytes immediately
after them. For .hex inputs the output is itself a valid Intel HEX file
covering that same data-plus-CRC region, so it can be reloaded/verified with
standard tools; .bin/.out outputs are the same bytes as a raw binary file.
"""

import os
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class CrcAlgorithm:
    name: str
    width: int
    poly: int
    init: int
    refin: bool
    refout: bool
    xorout: int


CRC32 = CrcAlgorithm(
    name="CRC-32",
    width=32,
    poly=0x04C11DB7,
    init=0xFFFFFFFF,
    refin=True,
    refout=True,
    xorout=0xFFFFFFFF,
)

DEFAULT_ALGORITHM = CRC32


class FirmwareParseError(ValueError):
    """Raised when a firmware file cannot be parsed or does not cover the
    requested address range."""


def _reflect(value: int, width: int) -> int:
    result = 0
    for _ in range(width):
        result = (result << 1) | (value & 1)
        value >>= 1
    return result


def compute_crc(data: bytes, algorithm: CrcAlgorithm = DEFAULT_ALGORITHM) -> int:
    """Compute a CRC over data using the Rocksoft-model bit-by-bit algorithm.

    This is the one place the algorithm parameters are used - swap the
    `algorithm` argument (or DEFAULT_ALGORITHM) to change poly/init/
    reflection/xorout/width later without touching any other code.
    """
    width = algorithm.width
    mask = (1 << width) - 1
    top_bit = 1 << (width - 1)
    crc = algorithm.init & mask

    for byte in data:
        if algorithm.refin:
            byte = _reflect(byte, 8)
        crc ^= byte << (width - 8)
        for _ in range(8):
            if crc & top_bit:
                crc = ((crc << 1) ^ algorithm.poly) & mask
            else:
                crc = (crc << 1) & mask

    if algorithm.refout:
        crc = _reflect(crc, width)

    return (crc ^ algorithm.xorout) & mask


def _self_test() -> None:
    check = compute_crc(b"123456789", CRC32)
    if check != 0xCBF43926:
        raise AssertionError(f"CRC-32 self-test failed: expected 0xCBF43926, got {check:#010X}")


_self_test()


def _read_bin_range(file_path: str, start_address: int, end_address: int) -> bytes:
    """.bin/.out files are treated as a raw firmware image that begins at the
    configured Starting Address (there is no in-file addressing metadata)."""
    range_size = end_address - start_address + 1

    with open(file_path, "rb") as handle:
        raw = handle.read()

    if len(raw) < range_size:
        raise FirmwareParseError("No firmware data found within the specified address range.")

    return raw[:range_size]


def _parse_intel_hex(file_path: str) -> Dict[int, int]:
    """Parse an Intel HEX file into a sparse {absolute_address: byte} map.

    Handles data records (00), EOF (01), extended segment address (02), and
    extended linear address (04) records, and verifies each record's
    checksum so a corrupted file is reported rather than silently misread.
    """
    memory: Dict[int, int] = {}
    upper_address = 0  # contributed by the most recent 02/04 record

    with open(file_path, "r", encoding="ascii", errors="strict") as handle:
        lines = handle.readlines()

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise FirmwareParseError(f"Line {line_number}: Intel HEX records must start with ':'.")

        try:
            payload = bytes.fromhex(line[1:])
        except ValueError as exc:
            raise FirmwareParseError(f"Line {line_number}: invalid hexadecimal record data.") from exc

        if len(payload) < 5:
            raise FirmwareParseError(f"Line {line_number}: record is too short to be valid.")

        byte_count = payload[0]
        record_address = (payload[1] << 8) | payload[2]
        record_type = payload[3]
        data = payload[4:4 + byte_count]
        checksum = payload[4 + byte_count]

        if len(data) != byte_count:
            raise FirmwareParseError(f"Line {line_number}: declared byte count does not match record length.")

        computed_checksum = (-(sum(payload[:4 + byte_count]))) & 0xFF
        if computed_checksum != checksum:
            raise FirmwareParseError(f"Line {line_number}: checksum mismatch (corrupted Intel HEX record).")

        if record_type == 0x00:  # data
            base = upper_address + record_address
            for offset, value in enumerate(data):
                memory[base + offset] = value
        elif record_type == 0x01:  # end of file
            break
        elif record_type == 0x02:  # extended segment address
            upper_address = (int.from_bytes(data, "big") << 4) & 0xFFFFFFFF
        elif record_type == 0x04:  # extended linear address
            upper_address = (int.from_bytes(data, "big") << 16) & 0xFFFFFFFF
        elif record_type in (0x03, 0x05):  # start segment/linear address - not firmware data
            continue
        else:
            raise FirmwareParseError(f"Line {line_number}: unsupported Intel HEX record type {record_type:#04X}.")

    return memory


def _read_hex_range(file_path: str, start_address: int, end_address: int) -> bytes:
    memory = _parse_intel_hex(file_path)

    missing: List[int] = [
        address for address in range(start_address, end_address + 1) if address not in memory
    ]
    if missing:
        raise FirmwareParseError("No firmware data found within the specified address range.")

    return bytes(memory[address] for address in range(start_address, end_address + 1))


def extract_firmware_range(file_path: str, file_type: str, start_address: int, end_address: int) -> bytes:
    """Return the actual firmware bytes for [start_address, end_address] (inclusive)."""
    file_type = (file_type or "").lower().lstrip(".")

    if file_type == "hex":
        return _read_hex_range(file_path, start_address, end_address)
    if file_type in ("bin", "out"):
        return _read_bin_range(file_path, start_address, end_address)

    raise FirmwareParseError(f"Unsupported firmware file type '.{file_type}' for CRC calculation.")


def _build_hex_output(data_with_crc: bytes, start_address: int) -> str:
    lines = []
    address = start_address
    for offset in range(0, len(data_with_crc), 16):
        chunk = data_with_crc[offset:offset + 16]
        payload = bytes([len(chunk), (address >> 8) & 0xFF, address & 0xFF, 0x00]) + chunk
        checksum = (-(sum(payload))) & 0xFF
        lines.append(":" + payload.hex().upper() + f"{checksum:02X}")
        address += len(chunk)
    lines.append(":00000001FF")  # EOF record
    return "\n".join(lines) + "\n"


def build_output_file(
    file_path: str,
    file_type: str,
    start_address: int,
    end_address: int,
    data: bytes,
    crc_value: int,
    algorithm: CrcAlgorithm = DEFAULT_ALGORITHM,
):
    """Build the "<name>_crc<ext>" output content: the hashed data followed by
    the CRC value, in the same format as the source file. Returns raw bytes
    for .bin/.out, or Intel HEX text (still returned as bytes) for .hex.
    """
    crc_bytes = crc_value.to_bytes(algorithm.width // 8, byteorder="big")
    data_with_crc = data + crc_bytes

    file_type = (file_type or "").lower().lstrip(".")
    if file_type == "hex":
        return _build_hex_output(data_with_crc, start_address).encode("ascii")
    return data_with_crc


def calculate_crc(
    file_path: str,
    start_address: int,
    end_address: int,
    algorithm: CrcAlgorithm = DEFAULT_ALGORITHM,
) -> dict:
    """Calculate the CRC of the firmware bytes in [start_address, end_address].

    Returns a structured dict describing exactly what was hashed, plus the
    ready-to-save output file bytes. Raises ValueError/FirmwareParseError on
    any problem - callers must not treat a raised exception as "calculated".
    """
    if start_address > end_address:
        raise ValueError("Starting Address cannot be greater than Ending Address.")

    file_type = os.path.splitext(file_path)[1][1:].lower()
    data = extract_firmware_range(file_path, file_type, start_address, end_address)

    expected_size = end_address - start_address + 1
    if len(data) != expected_size:
        raise FirmwareParseError("No firmware data found within the specified address range.")

    crc_value = compute_crc(data, algorithm)
    output_bytes = build_output_file(file_path, file_type, start_address, end_address, data, crc_value, algorithm)

    return {
        "start_address": start_address,
        "end_address": end_address,
        "data_size": len(data),
        "algorithm": algorithm.name,
        "crc": crc_value,
        "crc_hex": f"0x{crc_value:0{algorithm.width // 4}X}",
        "output_bytes": output_bytes,
    }
