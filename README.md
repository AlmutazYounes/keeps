# Local photos

A private gallery for a Google Photos takeout. Photos already live in `Photos/YYYY/MM-Month/`. The site runs on your machine at http://127.0.0.1:8765.

## What stays off GitHub

The pictures, the face database, the captions, the thumbnails, and the model weights are not in this repo. `.gitignore` keeps them local.

The scripts look for the library at `/Volumes/SamsungT7/Google Photos Backup`. Change `ROOT` in each script if your copy lives somewhere else.

## Gallery

The server uses only the Python standard library.

```bash
python3 gallery/server.py
```

It reads the folders once, when it starts. A file added after that stays invisible until you start the server again.

Photos, Videos, and Faces share one dark theme. The theme choice is saved in the browser.

Search matches the file name, a person's name, and the description once a photo has one.

## Sort a takeout

```bash
python3 sort_photos.py
```

Album copies of the same photo are kept once. Dates come from the Takeout metadata, then from the file name. The script copies files. It does not edit the photo bytes.

## Faces

Two ONNX files have to sit in `gallery/models/` before the face index will run:

- `10g_bnkps.onnx` finds faces
- `arcface_w600k_r50_batch.onnx` turns a face into a vector

Those weights are not shipped here.

```bash
python3 -m venv gallery/.venv
gallery/.venv/bin/pip install -r requirements.txt
gallery/.venv/bin/python gallery/index_faces.py
```

People in fewer than 10 photos stay off the Faces page. Giving the same name to two groups merges them into one person.

The index records a path when it finishes that photo. Run it again after you add pictures. It skips paths it already finished. It does not notice a new file by itself.

## Descriptions

Captions come from Florence-2, the ONNX build at `onnx-community/Florence-2-base-ft` on Hugging Face. Download these into `gallery/models/florence2/`:

- `tokenizer.json` and the other tokenizer files from the repo root
- `onnx/vision_encoder_q4f16.onnx`
- `onnx/embed_tokens_q4f16.onnx`
- `onnx/encoder_model_q4f16.onnx`
- `onnx/decoder_model_q4f16.onnx`
- `onnx/decoder_model_merged_q4.onnx`

```bash
gallery/.venv/bin/python gallery/index_captions.py
```

Each still photo gets a short paragraph. Search uses that text. The job walks the folders when it starts, then works through that list. A photo added after the walk waits for the next run. A photo whose file time changed is described again.

## New photos

Nothing watches the folders.

1. Put the file under `Photos/`.
2. Start `gallery/server.py` again so the grid can see it.
3. Run `gallery/index_faces.py` so the face index picks it up.
4. Run `gallery/index_captions.py` so it gets a description.

Videos show in the Videos tab. The face index and the caption index only read still photos.
