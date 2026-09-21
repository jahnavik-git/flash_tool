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

IMPORTANT - logical offsets vs. absolute addresses:
The UI's Starting/Ending Address fields (0x000000-0x3FFFFF, see
validators.MIN_ADDRESS/MAX_ADDRESS) are always a LOGICAL offset range into
"the firmware image", never an absolute MCU address. Intel HEX files, on
the other hand, carry real absolute addresses (e.g. an SSBL linked at
0x10000000), via Extended Linear/Segment Address records. So for .hex
inputs this module first parses the file into an absolute address map,
finds the firmware image's base address from the data itself (see
_find_firmware_region), and only then treats "0x000000" as "byte 0 of that
image" - i.e. logical_offset = absolute_address - firmware_base_address.
.bin/.out files have no addressing metadata at all, so for them the file's
own byte 0 is defined to be Starting Address (unchanged from before).

OUTPUT FILE: the generated "<name>_crc<ext>" file contains exactly the
verified firmware bytes for the requested range - nothing more. This project
does not define a policy for WHERE a CRC value should be embedded inside a
firmware image (a fixed trailer offset, a vector-table slot, a padded
region, ...), and guessing one would risk producing an output file that
looks valid but is wrong for the real target. So CRC *calculation* and CRC
*insertion* are kept separate: the computed value is reported in
calculate_crc()'s return value (and shown in the UI / API response), while
the output file itself is an unmodified, re-encoded copy of the exact bytes
that were hashed (using real absolute addressing for .hex, so it stays a
valid, reloadable Intel HEX file - not the logical 0x000000-based offsets).
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Tuple


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
        raise FirmwareParseError("No firmware data found within the selected address range.")

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


def _find_firmware_region(memory: Dict[int, int]) -> int:
    """Return the base (lowest) absolute address of the firmware image
    represented by an Intel HEX address map.

    Intel HEX addresses are absolute MCU addresses (e.g. 0x10000000), while
    the UI's Starting/Ending Address fields are logical offsets (0x000000-
    0x3FFFFF) into that image - they must never be compared to `memory`'s
    keys directly. A HEX file could in principle contain more than one disjoint
    address block (e.g. a small config/vector block plus the main firmware
    body); since this project does not define which one is "the" SSBL
    firmware region, this picks the LARGEST contiguous run of addresses as
    the firmware image and uses its lowest address as the base - the main
    firmware body is virtually always the largest contiguous block in a
    single-purpose HEX file like an SSBL image.
    """
    if not memory:
        raise FirmwareParseError("No firmware data found within the selected address range.")

    sorted_addresses = sorted(memory)
    runs: List[Tuple[int, int]] = []
    run_start = sorted_addresses[0]
    previous = sorted_addresses[0]
    for address in sorted_addresses[1:]:
        if address != previous + 1:
            runs.append((run_start, previous))
            run_start = address
        previous = address
    runs.append((run_start, previous))

    region_start, _region_end = max(runs, key=lambda run: run[1] - run[0])
    return region_start


def _read_hex_range(file_path: str, start_address: int, end_address: int) -> Tuple[bytes, int]:
    """Return (data, firmware_base_address) for the logical offset range
    [start_address, end_address] within the HEX file's firmware image.

    logical_offset = absolute_address - firmware_base_address, so the
    lookup below converts the other way: absolute_address = base + offset.
    """
    memory = _parse_intel_hex(file_path)
    base_address = _find_firmware_region(memory)

    missing = [
        offset for offset in range(start_address, end_address + 1)
        if (base_address + offset) not in memory
    ]
    if missing:
        raise FirmwareParseError("No firmware data found within the selected address range.")

    data = bytes(memory[base_address + offset] for offset in range(start_address, end_address + 1))
    return data, base_address


def _build_hex_output(data: bytes, absolute_start_address: int) -> str:
    """Re-encode `data` as a valid Intel HEX file starting at its real
    absolute address, emitting Extended Linear Address (04) records
    whenever the upper 16 bits change so addresses above 0xFFFF stay valid.
    """
    lines = []
    address = absolute_start_address
    current_upper = None

    for offset in range(0, len(data), 16):
        chunk = data[offset:offset + 16]

        upper = (address >> 16) & 0xFFFF
        if upper != current_upper:
            upper_payload = bytes([2, 0x00, 0x00, 0x04]) + upper.to_bytes(2, "big")
            upper_checksum = (-(sum(upper_payload))) & 0xFF
            lines.append(":" + upper_payload.hex().upper() + f"{upper_checksum:02X}")
            current_upper = upper

        low_address = address & 0xFFFF
        payload = bytes([len(chunk), (low_address >> 8) & 0xFF, low_address & 0xFF, 0x00]) + chunk
        checksum = (-(sum(payload))) & 0xFF
        lines.append(":" + payload.hex().upper() + f"{checksum:02X}")
        address += len(chunk)

    lines.append(":00000001FF")  # EOF record
    return "\n".join(lines) + "\n"


def build_output_file(file_type: str, data: bytes, absolute_start_address: int) -> bytes:
    """Build the "<name>_crc<ext>" output content: exactly the verified
    firmware bytes, in the same format as the source file - see the module
    docstring for why the CRC value itself is not embedded into this file.
    """
    file_type = (file_type or "").lower().lstrip(".")
    if file_type == "hex":
        return _build_hex_output(data, absolute_start_address).encode("ascii")
    return bytes(data)


def calculate_crc(
    file_path: str,
    start_address: int,
    end_address: int,
    algorithm: CrcAlgorithm = DEFAULT_ALGORITHM,
) -> dict:
    """Calculate the CRC of the firmware bytes in the logical offset range
    [start_address, end_address] (always 0x000000-0x3FFFFF per the UI's
    range validation - see the module docstring for how that maps onto an
    Intel HEX file's real absolute addresses).

    Returns a structured dict describing exactly what was hashed, plus the
    ready-to-save output file bytes. Raises ValueError/FirmwareParseError on
    any problem - callers must not treat a raised exception as "calculated".
    """
    if start_address > end_address:
        raise ValueError("Starting Address must be less than or equal to Ending Address.")

    file_type = os.path.splitext(file_path)[1][1:].lower()

    if file_type == "hex":
        data, firmware_base_address = _read_hex_range(file_path, start_address, end_address)
        absolute_start_address = firmware_base_address + start_address
    elif file_type in ("bin", "out"):
        data = _read_bin_range(file_path, start_address, end_address)
        absolute_start_address = start_address
    else:
        raise FirmwareParseError(f"Unsupported firmware file type '.{file_type}' for CRC calculation.")

    expected_size = end_address - start_address + 1
    if len(data) != expected_size:
        raise FirmwareParseError("No firmware data found within the selected address range.")

    crc_value = compute_crc(data, algorithm)
    output_bytes = build_output_file(file_type, data, absolute_start_address)

    return {
        "start_address": start_address,
        "end_address": end_address,
        "data_size": len(data),
        "algorithm": algorithm.name,
        "crc": crc_value,
        "crc_hex": f"0x{crc_value:0{algorithm.width // 4}X}",
        "output_bytes": output_bytes,
    }
