from flask import Flask, render_template, request
from pathlib import Path
from flask import jsonify
from werkzeug.utils import secure_filename
from uuid import uuid4
import shutil

app = Flask(__name__)

UPLOAD_FOLDER = Path(__file__).parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

active_uploads = {}


@app.route("/")
def index():
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]

    destination = UPLOAD_FOLDER / file.filename
    file.save(destination)

    return f"Uploaded {file.filename}"


@app.route("/upload-chunk", methods =["POST"])

def upload_chunk():

    chunk = request.files.get("chunk")
    filename = secure_filename(request.form.get("filename", ""))
    upload_id = request.form.get("upload_id", "")

    try:
        index = int(request.form.get("index", "-1"))
        total = int(request.form.get("total", "0"))
    except ValueError:
         return jsonify(error="Invalid chunk information"), 400

    if chunk is None or not filename or total < 1 or not 0 <= index < total:
        return jsonify(error="Invalid upload"), 400

    if index == 0:
        upload_id = uuid4().hex
        active_uploads[upload_id] = {
            "filename": filename,
            "total": total,
            "next_index": 0
        }

    upload = active_uploads.get(upload_id)

    if upload is None:
        return jsonify(error="Unknown upload"), 400

    if (upload["next_index"] != index
            or upload["filename"] != filename
            or upload["total"] != total):
        return jsonify(error="Unexpected chunk"), 400

    temporary_file = UPLOAD_FOLDER / f"{upload_id}.part"

    with temporary_file.open("ab") as output:
        shutil.copyfileobj(chunk.stream, output)

    upload["next_index"] += 1

    if upload["next_index"] == total:

        saved_name = f"{upload_id}_{filename}"
        temporary_file.rename(UPLOAD_FOLDER / saved_name)

        del active_uploads[upload_id]
        return jsonify(
            upload_id=upload_id,
            complete=True,
            filename=saved_name
        )

    return jsonify(upload_id=upload_id, complete=False)

    
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)