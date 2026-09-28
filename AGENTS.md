# Agent notes

Use this when you clone the repo and need to run it. The photo library is not in git.

## What you get from the clone

Source only. You do not get pictures, face rows, captions, thumbnails, or model weights. `.gitignore` keeps those local.

## Layout

The repo root is the library root. These paths are relative to it.

- `Photos/` holds the sorted library, `YYYY/MM-Month/`.
- `takeout-*.zip` sits in the repo root, next to `sort_photos.py`. Not inside `Photos/`.
- `gallery/server.py` is the site.
- `gallery/.venv/` is the indexer environment. Create it locally.
- `gallery/models/` holds ONNX weights. They are not in git.
- `gallery/faces/`, `gallery/captions/`, and `gallery/jobs/` are sqlite databases created on first run.
- `gallery/cache/` holds thumbnails.

## Set the library path

Every script currently points at `/Volumes/SamsungT7/Google Photos Backup`. Change `ROOT` to the absolute path of this clone before you run anything. Use the same path in each file:

- `sort_photos.py`
- `gallery/server.py`
- `gallery/faces_db.py`
- `gallery/faces_lib.py`
- `gallery/captions_db.py`
- `gallery/caption_lib.py`
- `gallery/jobs_db.py`

## Run the gallery

From the repo root, with system Python 3:

```bash
python3 gallery/server.py
```

Open http://127.0.0.1:8765. The server uses only the standard library. It scans `Photos/` once at startup.

Still thumbnails use `sips`. Video frames use `ffmpeg`. Both are expected on macOS. `ffmpeg` is required for video tiles.

A restart reads the face and caption databases. It does not repeat finished still photos. It starts `gallery/index_faces.py` and `gallery/index_captions.py` only for still photos that are missing or whose file time changed. It starts them only if `gallery/.venv/bin/python` exists, and it will not start a second copy of a job that is already running.

Settings shows synced, remaining, and whether a job is in progress.

## Install the indexer

Do this only when the model files below are already in `gallery/models/`. If the venv exists and the weights do not, the server will start the jobs and they will fail.

```bash
python3 -m venv gallery/.venv
gallery/.venv/bin/pip install -r requirements.txt
```

Face weights, not in this repo:

- `gallery/models/10g_bnkps.onnx`
- `gallery/models/arcface_w600k_r50_batch.onnx`

Caption weights, from `onnx-community/Florence-2-base-ft` on Hugging Face. The code loads these paths:

- `gallery/models/florence2/tokenizer.json`
- `gallery/models/florence2/onnx/vision_encoder_q4f16.onnx`
- `gallery/models/florence2/onnx/embed_tokens_q4f16.onnx`
- `gallery/models/florence2/onnx/encoder_model_q4f16.onnx`
- `gallery/models/florence2/onnx/decoder_model_q4f16.onnx`
- `gallery/models/florence2/onnx/decoder_model_merged_q4.onnx`

Download them with the venv after `pip install`:

```bash
gallery/.venv/bin/python - <<'PY'
from huggingface_hub import hf_hub_download
from pathlib import Path
repo = "onnx-community/Florence-2-base-ft"
dest = Path("gallery/models/florence2")
names = [
    "tokenizer.json",
    "onnx/vision_encoder_q4f16.onnx",
    "onnx/embed_tokens_q4f16.onnx",
    "onnx/encoder_model_q4f16.onnx",
    "onnx/decoder_model_q4f16.onnx",
    "onnx/decoder_model_merged_q4.onnx",
]
for name in names:
    print(hf_hub_download(repo, name, local_dir=dest))
PY
```

You can also start the jobs by hand from the repo root:

```bash
gallery/.venv/bin/python gallery/index_faces.py
gallery/.venv/bin/python gallery/index_captions.py
```

People in fewer than 10 photos stay off the Faces page. The same name on two groups merges them. Captions are short paragraphs. Search uses the file name, the person name, and the caption. Videos are not sent through either index.

## Sort a Takeout

Only for zip files named `takeout-*.zip` in the repo root. Do not unzip them first. The script stops if the disk has less than 20 GiB free. It copies into `Photos/` and does not edit photo bytes.

```bash
python3 sort_photos.py
```

Do not run it for a file you dropped straight into `Photos/`. For that file, restart `gallery/server.py`.

## Do not commit

Do not commit `Photos/`, `takeout-*.zip`, `gallery/.venv/`, `gallery/cache/`, `gallery/faces/`, `gallery/captions/`, `gallery/jobs/`, `gallery/dispose/`, `gallery/models/`, `_sort.log`, or `_sort_state.sqlite`. Do not edit original photo bytes.
