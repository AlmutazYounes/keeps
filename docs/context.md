# Context

## What this is

A private gallery for one Google Photos takeout. The pictures stay on this drive. The site runs on this Mac so the library can be browsed, searched, and cleaned here.

## Who uses it

Me, on this Mac.

## Status

The gallery is in use on this drive. Main has search, faces, captions, categories, selection, and the place map. A review pass can list disposable photos. Nothing is chosen as the next change.

## Stack

Python 3. gallery/server.py uses the standard library. Face and caption jobs use gallery/.venv with onnxruntime. Data is sqlite. Thumbnails use sips and ffmpeg.

## How to run it

The repo root is the library root. Each script sets ROOT to /Volumes/SamsungT7/Google Photos Backup. Change that path in every file before running a clone that lives somewhere else. The files are sort_photos.py, gallery/server.py, gallery/faces_db.py, gallery/faces_lib.py, gallery/captions_db.py, gallery/caption_lib.py, gallery/jobs_db.py, gallery/dispose_db.py, and gallery/index_dispose.py.

From the repo root:

```bash
python3 gallery/server.py
```

Open http://127.0.0.1:8765. The server scans Photos/ once at startup. A restart reads the face and caption databases and does not repeat a finished still photo. It starts gallery/index_faces.py and gallery/index_captions.py only when gallery/.venv/bin/python exists, and only for still photos that are missing or whose file time changed. It will not start a second copy of a job that is already running.

Create the indexer only when the model files are already in gallery/models/. If the venv exists and the weights do not, the jobs start and fail.

```bash
python3 -m venv gallery/.venv
gallery/.venv/bin/pip install -r requirements.txt
```

Face weights, not in this repo:

- gallery/models/10g_bnkps.onnx
- gallery/models/arcface_w600k_r50_batch.onnx

Caption weights, from onnx-community/Florence-2-base-ft. Download them with the venv after pip install:

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

The jobs can also be started by hand from the repo root:

```bash
gallery/.venv/bin/python gallery/index_faces.py
gallery/.venv/bin/python gallery/index_captions.py
```

Sort a takeout only for zip files named takeout-*.zip in the repo root. Do not unzip them first. The script stops if the disk has less than 20 GiB free.

```bash
python3 sort_photos.py
```

Do not run that script for a file dropped straight into Photos/. Restart gallery/server.py for that file.

## How to check it

```bash
python3 -m unittest discover -s gallery -p 'test_*.py'
```

## How to deploy it

There is no deploy. Run the server on this Mac.

## Links

https://github.com/AlmutazYounes/keeps

## Env var names

None.

## Folders

- Photos/ holds the sorted library, YYYY/MM-Month/. It is not in git.
- takeout-*.zip sits in the repo root, next to sort_photos.py.
- gallery/server.py is the site. gallery/static/ holds the pages.
- gallery/.venv/ is the indexer environment.
- gallery/models/ holds ONNX weights.
- gallery/faces/, gallery/captions/, gallery/jobs/, and gallery/dispose/ are sqlite databases created on first use.
- gallery/cache/ holds thumbnails and the place-name cache.
- _sort_state.sqlite and _sort.log track a takeout import.
- docs/ holds this context, the story, and decisions.

Do not commit Photos/, takeout-*.zip, gallery/.venv/, gallery/cache/, gallery/faces/, gallery/captions/, gallery/jobs/, gallery/dispose/, gallery/models/, _sort.log, or _sort_state.sqlite. Do not edit original photo bytes.

## Open questions

None.
