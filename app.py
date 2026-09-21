import os
import tempfile
import uuid

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

from flash_service import flash_firmware
from validators import MAX_UPLOAD_SIZE, validate_address_order, validate_file_upload, validate_hex_address


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE
# /tmp is the only writable path on serverless platforms like Vercel; it also
# works fine for local development.
app.config["UPLOAD_FOLDER"] = os.path.join(tempfile.gettempdir(), "azimuth-flash-uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Each firmware unit the form submits, keyed by its flat form-field prefix.
FIRMWARE_UNITS = (
    ("core0_ssbl", "Core 0 SSBL"),
    ("core0_application", "Core 0 Application"),
    ("core1_application", "Core 1 Application"),
)


def cleanup_uploads(*paths):
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


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
            file_path = validate_file_upload(file_field, display_name, MAX_UPLOAD_SIZE)

            source_address = validate_hex_address(
                request.form.get(f"{form_prefix}_source_address", ""), f"{display_name} source address"
            )
            destination_address = validate_hex_address(
                request.form.get(f"{form_prefix}_destination_address", ""), f"{display_name} destination address"
            )
            validate_address_order(source_address, destination_address, display_name)

            filename = f"{uuid.uuid4().hex}_{secure_filename(file_path)}"
            upload_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file_field.save(upload_path)
            upload_paths.append(upload_path)

            units[form_prefix] = {
                "file": upload_path,
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

        result = flash_firmware(core_config)

        if result["status"] == "success":
            return jsonify({"success": True, "stage": result["stage"], "percent": result["percent"], "data": result})

        return jsonify(
            {"success": False, "stage": result["stage"], "percent": result["percent"], "error": result["error"]}
        ), 400

    except ValueError as exc:
        return jsonify({"success": False, "stage": "Preparing", "percent": 0, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify(
            {"success": False, "stage": "Preparing", "percent": 0, "error": f"Flash failed. Reason: {exc}"}
        ), 500
    finally:
        cleanup_uploads(*upload_paths)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
