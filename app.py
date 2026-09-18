import os
import threading
import uuid

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

from flash_service import flash_firmware
from validators import MAX_UPLOAD_SIZE, validate_file_upload, validate_hex_address


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

FLASH_JOBS = {}
FLASH_JOBS_LOCK = threading.Lock()

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


def _update_job(job_id, **fields):
    with FLASH_JOBS_LOCK:
        job = FLASH_JOBS.get(job_id)
        if job is not None:
            job.update(fields)


def _run_flash_job(job_id, core_config, upload_paths):
    def progress_callback(stage, percent):
        _update_job(job_id, stage=stage, percent=percent, status="running", error=None)

    try:
        result = flash_firmware(core_config, progress_callback)
        _update_job(job_id, status="success", stage="Completed", percent=100, error=None, result=result)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the polling client
        _update_job(job_id, status="failed", error=str(exc))
    finally:
        cleanup_uploads(*upload_paths)


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

            filename = secure_filename(file_path)
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

        job_id = uuid.uuid4().hex
        with FLASH_JOBS_LOCK:
            FLASH_JOBS[job_id] = {"status": "running", "stage": "Preparing", "percent": 0, "error": None, "result": None}

        thread = threading.Thread(
            target=_run_flash_job, args=(job_id, core_config, tuple(upload_paths)), daemon=True
        )
        thread.start()

        return jsonify({"success": True, "job_id": job_id})

    except ValueError as exc:
        cleanup_uploads(*upload_paths)
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        cleanup_uploads(*upload_paths)
        return jsonify({"success": False, "error": f"Flash failed. Reason: {exc}"}), 500


@app.route("/api/flash/status/<job_id>", methods=["GET"])
def api_flash_status(job_id):
    with FLASH_JOBS_LOCK:
        job = FLASH_JOBS.get(job_id)
        if job is None:
            return jsonify({"success": False, "error": "Unknown flash job."}), 404
        payload = dict(job)

        if job["status"] in ("success", "failed"):
            FLASH_JOBS.pop(job_id, None)

    payload["success"] = True
    return jsonify(payload)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
