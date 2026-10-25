
from flask import Flask, render_template, request
from pathlib import Path, PureWindowsPath
from flask import jsonify
from werkzeug.utils import secure_filename
from uuid import uuid4
import hashlib
import hmac
import json
import os

app = Flask(__name__)

UPLOAD_FOLDER = Path(
    os.environ.get("MEDIA_FOLDER", str(Path(__file__).parent / "uploads"))
)
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

STATE_FOLDER = UPLOAD_FOLDER / ".upload_state"
STATE_FOLDER.mkdir(exist_ok=True)


def save_upload_state(upload_id, upload):
    state_file = STATE_FOLDER / f"{upload_id}.json"
    temp_file = STATE_FOLDER / f"{upload_id}.tmp"

    temp_file.write_text(json.dumps(upload), encoding="utf-8")
    temp_file.replace(state_file)


def load_upload_states():
    uploads = {}

    for state_file in STATE_FOLDER.glob("*.json"):
        upload_id = state_file.stem
        temporary_file = UPLOAD_FOLDER / f"{upload_id}.part"

        if not temporary_file.exists():
            continue

        try:
            upload = json.loads(
                state_file.read_text(encoding="utf-8")
            )
            uploads[upload_id] = upload

        except (OSError, json.JSONDecodeError):
            print(f"Could not restore upload {upload_id}")

    return uploads


active_uploads = load_upload_states()

print(f"Restored {len(active_uploads)} unfinished uploads")


@app.route("/")
def index():
    return render_template("upload.html")


@app.route("/upload-status", methods=["GET"])
def upload_status():

    upload_id = request.args.get("upload_id", "")

    upload = active_uploads.get(upload_id)

    if upload is None:
        return jsonify(error="Unknown upload"), 404

    temporary_file = UPLOAD_FOLDER / f"{upload_id}.part"

    if (not temporary_file.exists()
            or temporary_file.stat().st_size < upload["bytes_received"]):
        return jsonify(error="Missing or incomplete upload data"), 409

    return jsonify(
        upload_id=upload_id,
        filename=upload["filename"],
        total=upload["total"],
        next_index=upload["next_index"],
        bytes_received=upload["bytes_received"]
    )


@app.route("/upload-chunk", methods=["POST"])
def upload_chunk():

    chunk = request.files.get("chunk")
    filename = secure_filename(request.form.get("filename", ""))
    upload_id = request.form.get("upload_id", "")

    try:
        index = int(request.form.get("index", "-1"))
        total = int(request.form.get("total", "0"))
    except ValueError:
        return jsonify(error="Invalid chunk information"), 400

    relative_path = request.form.get("relative_path", filename)
    parts = relative_path.split("/")

    if any(
        not p or p in (".", "..")
        or p.endswith((".", " "))
        or any(c in '<>:"\\|?*' or ord(c) < 32 for c in p)
        or PureWindowsPath(p).is_reserved()
        for p in parts
    ):
        return jsonify(error="Invalid movie path"), 400

    destination = UPLOAD_FOLDER.joinpath(*parts)

    if not destination.resolve().is_relative_to(UPLOAD_FOLDER.resolve()):
        return jsonify(error="Invalid destination"), 400

    if index == 0 and destination.exists():
        return jsonify(error="File already exists"), 409

    if chunk is None or not filename or total < 1 or not 0 <= index < total:
        return jsonify(error="Invalid upload"), 400

    expected_hash = request.form.get("sha256", "")

    chunk_data = chunk.read(1024 * 1024 + 1)

    if not chunk_data or len(chunk_data) > 1024 * 1024:
        return jsonify(error="Invalid chunk size"), 400

    actual_hash = hashlib.sha256(chunk_data).hexdigest()

    if not hmac.compare_digest(actual_hash, expected_hash):
        return jsonify(error="Chunk integrity verification failed"), 422

    print(f"Chunk {index}: SHA-256 verified")

    if index == 0:
        upload_id = uuid4().hex
        active_uploads[upload_id] = {
            "filename": filename,
            "total": total,
            "next_index": 0,
            "bytes_received": 0,
            "relative_path": relative_path,
        }

    upload = active_uploads.get(upload_id)

    if upload is None:
        return jsonify(error="Unknown upload"), 400

    if (upload["next_index"] != index
            or upload["filename"] != filename
            or upload["total"] != total
            or upload.get("relative_path", filename) != relative_path):
        return jsonify(error="Unexpected chunk"), 400

    temporary_file = UPLOAD_FOLDER / f"{upload_id}.part"

    expected_size = upload["bytes_received"]

    if expected_size > 0 and not temporary_file.exists():
        return jsonify(error="Missing partial upload data"), 409

    if temporary_file.exists():
        if temporary_file.stat().st_size < expected_size:
            return jsonify(error="Incomplete saved upload"), 409

    with temporary_file.open("ab") as output:
        output.truncate(expected_size)
        output.write(chunk_data)

    upload["bytes_received"] += len(chunk_data)
    upload["next_index"] += 1

    if upload["next_index"] == total:

        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            return jsonify(error="File already exists"), 409

        temporary_file.rename(destination)

        (STATE_FOLDER / f"{upload_id}.json").unlink(missing_ok=True)

        del active_uploads[upload_id]

        return jsonify(
            upload_id=upload_id,
            complete=True,
            filename=relative_path
        )

    save_upload_state(upload_id, upload)

    return jsonify(upload_id=upload_id, complete=False)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
