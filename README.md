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

The library is the folder Keeps lives in. Settings can point it at another folder. The next start opens that folder.

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
