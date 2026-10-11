from flask import Flask, render_template, request
from pathlib import Path

app = Flask(__name__)

UPLOAD_FOLDER = Path(__file__).parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)


@app.route("/")
def index():
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]

    destination = UPLOAD_FOLDER / file.filename
    file.save(destination)

    return f"Uploaded {file.filename}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)