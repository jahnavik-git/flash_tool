import os
from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

from flash_service import flash_firmware
from validators import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE, validate_file_upload, validate_hex_address


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


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
    try:
        ssbl_file = request.files.get("ssbl_file")
        application_file = request.files.get("application_file")

        ssbl_path = validate_file_upload(ssbl_file, "SSBL", MAX_UPLOAD_SIZE)
        application_path = validate_file_upload(application_file, "application", MAX_UPLOAD_SIZE)

        ssbl_source_raw = request.form.get("ssbl_source_address", "")
        ssbl_destination_raw = request.form.get("ssbl_destination_address", "")
        application_source_raw = request.form.get("application_source_address", "")
        application_destination_raw = request.form.get("application_destination_address", "")

        ssbl_source = validate_hex_address(ssbl_source_raw, "SSBL source address")
        ssbl_destination = validate_hex_address(ssbl_destination_raw, "SSBL destination address")
        application_source = validate_hex_address(application_source_raw, "Application source address")
        application_destination = validate_hex_address(application_destination_raw, "Application destination address")

        if ssbl_source == 0 or ssbl_destination == 0 or application_source == 0 or application_destination == 0:
            raise ValueError("Address values cannot be zero.")

        ssbl_filename = secure_filename(ssbl_path)
        application_filename = secure_filename(application_path)

        ssbl_upload_path = os.path.join(app.config["UPLOAD_FOLDER"], ssbl_filename)
        application_upload_path = os.path.join(app.config["UPLOAD_FOLDER"], application_filename)

        ssbl_file.save(ssbl_upload_path)
        application_file.save(application_upload_path)

        try:
            result = flash_firmware(
                ssbl_upload_path,
                application_upload_path,
                ssbl_source,
                ssbl_destination,
                application_source,
                application_destination,
            )
            return jsonify({"success": True, "data": result})
        finally:
            cleanup_uploads(ssbl_upload_path, application_upload_path)

    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"Flash failed. Reason: {exc}"}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
