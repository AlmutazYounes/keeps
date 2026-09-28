# Local photos

A private gallery for a Google Photos takeout. Photos already live in `Photos/YYYY/MM-Month/`. The site runs on your machine at http://127.0.0.1:8765.

## Screenshots

These pictures use colored placeholders. They are not photos from anyone's library.

### Home

![Home page with placeholder memories, a day grid, and the date scrubber](docs/images/home.png)

### Faces

![Faces page with placeholder people](docs/images/faces.png)

### Settings

![Settings page with sample sync counts](docs/images/settings.png)

## What stays off GitHub

The pictures, the face database, the captions, the thumbnails, and the model weights are not in this repo. `.gitignore` keeps them local.

The scripts look for the library at `/Volumes/SamsungT7/Google Photos Backup`. Change `ROOT` in each script if your copy lives somewhere else.

## Download a Google Takeout

Do this once, from the Google account that owns the photos.

1. Open https://takeout.google.com.
2. Choose Deselect all.
3. Turn on Google Photos only.
4. Keep every album if you want the whole library.
5. Create the export as `.zip`. Google splits a large library into several zip files.
6. Wait for the email, then download every part.

Leave the names Google gives them. They look like `takeout-20260928T120000Z-001.zip`. The sorter only sees files that match `takeout-*.zip`. If a browser renames a download, rename it back.

Put every zip in the library folder, next to `sort_photos.py`. Do not put them inside `Photos/`. Do not unzip them yourself.

## Sort the Takeout

Run this only for those zip files. Skip it when the photos are already in `Photos/`, and skip it when you add a loose file later.

The disk needs at least 20 GiB free. The script stops if there is less.

```bash
python3 sort_photos.py
```

It reads the date from the Takeout metadata, then the file name, then the file itself. It copies each photo into `Photos/YYYY/MM-Month/`. Album copies of the same photo are kept once. The original bytes are not edited.

When the copy finishes, you are done with this script.

## Gallery

The server uses only the Python standard library.

```bash
python3 gallery/server.py
```

Open http://127.0.0.1:8765. It reads the folders once, when it starts. A file added after that stays invisible until you start the server again.

Photos, Videos, and Faces share one dark theme. The theme choice is saved in the browser.

Search matches the file name, a person's name, and the description once a photo has one.

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

Finished photos stay in the face database. A gallery restart runs this only for still photos that are not saved yet. You can also run the command above yourself. It skips paths it already finished.

## Descriptions

Captions come from Florence-2, the ONNX build at `onnx-community/Florence-2-base-ft` on Hugging Face. Download these into `gallery/models/florence2/`:

- `tokenizer.json`
- `onnx/vision_encoder_q4f16.onnx`
- `onnx/embed_tokens_q4f16.onnx`
- `onnx/encoder_model_q4f16.onnx`
- `onnx/decoder_model_q4f16.onnx`
- `onnx/decoder_model_merged_q4.onnx`

```bash
gallery/.venv/bin/python gallery/index_captions.py
```

Each still photo gets a short paragraph. Search uses that text. Finished captions stay in the database. A gallery restart describes only still photos that are missing or whose file time changed. A job that is already walking does not see a file added after it made its list. Restart the gallery after that file is in `Photos/`.

## New photos

Do not run `sort_photos.py` for these. That script is only for a fresh `takeout-*.zip`.

Face results and descriptions are saved in their databases. Stopping the gallery does not erase them, and starting it again does not repeat finished photos.

On startup the server compares the folders with those databases. It runs face recognition and descriptions only for still photos that are missing or were changed. Open Settings to see how many are synced, how many are left, and whether a job is in progress.

1. Put the file under `Photos/`.
2. Start `gallery/server.py` again.

The grid picks up the file from that scan. The two jobs then save the new photo and leave the rest alone.

Videos show in the Videos tab. The face index and the caption index only read still photos.

## For agents

Clone, path setup, the indexer, and the model files are in [AGENTS.md](AGENTS.md).
