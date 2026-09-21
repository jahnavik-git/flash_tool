import os
import tempfile
import time
import uuid

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

from crc_service import FirmwareParseError, calculate_crc
from flash_service import flash_firmware
from validators import MAX_UPLOAD_SIZE, validate_address_order, validate_file_upload, validate_hex_address


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE
# /tmp is the only writable path on serverless platforms like Vercel; it also
# works fine for local development.
app.config["UPLOAD_FOLDER"] = os.path.join(tempfile.gettempdir(), "azimuth-flash-uploads")
app.config["RESULTS_FOLDER"] = os.path.join(tempfile.gettempdir(), "azimuth-flash-results")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["RESULTS_FOLDER"], exist_ok=True)

# Each firmware unit the form submits, keyed by its flat form-field prefix.
FIRMWARE_UNITS = (
    ("core0_ssbl", "Core 0 SSBL"),
    ("core0_application", "Core 0 Application"),
    ("core1_application", "Core 1 Application"),
)

# Section headings used only in the CRC result file, matching the requested format.
CRC_SECTION_LABELS = {
    "core0_ssbl": "CORE 0 - SSBL",
    "core0_application": "CORE 0 - APPLICATION",
    "core1_application": "CORE 1 - APPLICATION",
}


def cleanup_uploads(*paths):
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def _file_extension(filename):
    return os.path.splitext(filename)[1][1:].lower() if os.path.splitext(filename)[1] else ""


def _build_crc_result_text(sections):
    lines = [
        "AZIMUTH FLASH UTILITY",
        "CRC CALCULATION RESULT",
        "=" * 30,
        "",
    ]
    for section in sections:
        lines.append(section["label"])
        lines.append(f"File: {section['file_name']}")
        lines.append(f"Starting Address: 0x{section['start_address']:04X}")
        lines.append(f"Ending Address:   0x{section['end_address']:04X}")
        lines.append(f"Data Size: {section['data_size']} bytes")
        lines.append(f"CRC Algorithm: {section['algorithm']}")
        lines.append(f"CRC: {section['crc_hex']}")
        lines.append("")

    lines.append("=" * 30)
    lines.append("CRC CALCULATION COMPLETED")
    lines.append("=" * 30)
    return "\n".join(lines) + "\n"


def _calculate_crc_for_units(units):
    """Compute CRC for every configured unit and write the result file.

    Raises on the first failure - callers must not treat a partial run as
    success, and no result file is written unless every section succeeds.
    """
    sections = []
    for form_prefix, _display_name in FIRMWARE_UNITS:
        unit = units[form_prefix]
        crc_info = calculate_crc(
            file_path=unit["file"],
            file_type=unit["file_type"],
            start_address=unit["start_address"],
            end_address=unit["end_address"],
            file_name=unit["original_name"],
        )
        crc_info["label"] = CRC_SECTION_LABELS[form_prefix]
        sections.append(crc_info)

    content = _build_crc_result_text(sections)
    result_filename = f"Azimuth_CRC_Result_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.txt"
    result_path = os.path.join(app.config["RESULTS_FOLDER"], result_filename)
    with open(result_path, "w", encoding="utf-8") as handle:
        handle.write(content)

    return {
        "status": "success",
        "filename": result_filename,
        "path": result_path,
        "content": content,
        "sections": sections,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/flash", methods=["POST"])
def api_flash():
    upload_paths = []
    try:
        units = {}
        for form_prefix, display_name in FIRMWARE_UNITS:
            file_field = request.files.get(f"{form_prefix}_file")
            original_name = validate_file_upload(file_field, display_name, MAX_UPLOAD_SIZE)

            source_address = validate_hex_address(
                request.form.get(f"{form_prefix}_source_address", ""), f"{display_name} source address"
            )
            destination_address = validate_hex_address(
                request.form.get(f"{form_prefix}_destination_address", ""), f"{display_name} destination address"
            )
            validate_address_order(source_address, destination_address, display_name)

            filename = f"{uuid.uuid4().hex}_{secure_filename(original_name)}"
            upload_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file_field.save(upload_path)
            upload_paths.append(upload_path)

            units[form_prefix] = {
                "file": upload_path,
                "original_name": original_name,
                "file_type": _file_extension(original_name),
                "start_address": source_address,
                "end_address": destination_address,
            }

        core_config = {
            "core0": {
                "ssbl": units["core0_ssbl"],
                "application": units["core0_application"],
            },
            "core1": {
                "application": units["core1_application"],
            },
        }

        flash_result = flash_firmware(core_config)

        if flash_result["status"] != "success":
            return jsonify(
                {
                    "success": False,
                    "stage": flash_result["stage"],
                    "percent": flash_result["percent"],
                    "error": flash_result["error"],
                    "crc": {"status": "skipped"},
                }
            ), 400

        try:
            crc_result = _calculate_crc_for_units(units)
            return jsonify(
                {
                    "success": True,
                    "stage": "CRC calculation completed",
                    "percent": 100,
                    "data": flash_result,
                    "crc": crc_result,
                }
            )
        except (FirmwareParseError, ValueError) as exc:
            return jsonify(
                {
                    "success": True,
                    "stage": "Calculating CRC",
                    "percent": 95,
                    "data": flash_result,
                    "crc": {"status": "failed", "error": f"CRC calculation failed: {exc}"},
                }
            )

    except ValueError as exc:
        return jsonify(
            {"success": False, "stage": "Preparing", "percent": 0, "error": str(exc), "crc": {"status": "skipped"}}
        ), 400
    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "stage": "Preparing",
                "percent": 0,
                "error": f"Flash failed. Reason: {exc}",
                "crc": {"status": "skipped"},
            }
        ), 500
    finally:
        cleanup_uploads(*upload_paths)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
