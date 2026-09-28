# Keeps

A private gallery for a Google Photos takeout.

## What it does

- Serves the library at http://127.0.0.1:8765
- Copies `takeout-*.zip` into `Photos/YYYY/MM-Month/`
- Searches by person, date, and caption on this machine

## Install

Python 3. From the repo root:

```bash
python3 gallery/server.py
```

The scripts look for `/Volumes/SamsungT7/Google Photos Backup`. Change `ROOT` if your copy lives somewhere else.

The rest of the setup is in [docs/guide.md](docs/guide.md).

## Example

```bash
python3 gallery/server.py
```

```
Scanning library...
Open http://127.0.0.1:8765
```

The indexed file count prints between those two lines.

## License

[MIT](LICENSE)
