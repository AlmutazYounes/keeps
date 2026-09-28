# D009 Thumbnails use macOS tools

Context

The grid needs small JPEGs. The gallery server stays on the Python standard library, so it does not carry an image library.

Decision

Still thumbnails and face crops use sips. Video frames use ffmpeg. Results are cached under gallery/cache/.

Consequences

The site expects a Mac with sips, and ffmpeg for video tiles. The cache is not in git, so the first view of a photo builds the thumbnail again.

Date

2026-09-28
