# D001 The gallery stays on this Mac

Context

The library is personal. A public site would need accounts, and the photos would leave this drive.

Decision

The server binds to 127.0.0.1 port 8765. There is no login. gallery/server.py uses only the Python standard library. Face and caption jobs run in gallery/.venv.

Consequences

Anyone on this Mac can open the site. A phone that is not on this machine cannot. The gallery starts without the model weights. Indexing waits until the venv and the weights are both present.

Date

2026-09-28
