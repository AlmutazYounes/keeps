# D008 The library path is hard-coded

Context

One drive holds this library. A settings screen would be extra machinery for a path that rarely moves.

Decision

ROOT is /Volumes/SamsungT7/Google Photos Backup in sort_photos.py, gallery/server.py, and the database and model modules. A clone on another machine has to set that same path in each of those files before it runs.

Consequences

There is no env var and no config file. Moving the drive means editing those files so they all match.

Date

2026-09-28
