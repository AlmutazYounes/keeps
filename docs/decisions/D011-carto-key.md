# D011 The map key stays off git

The light tile style in this decision was replaced by D012. The key rule still stands.

Context

CARTO raster tiles need a free API key. The Categories map uses those tiles for light and dark.

Decision

The key is one line in gallery/carto.key. The server inserts it into the Categories page. The file is not in git. Light and dark tiles keep their styles and add the key as a query parameter.

Consequences

A missing key file still serves the page. The tiles then show CARTO's watermark. Anyone who can open the page can read the key in the tile URL. Restart the server after the file changes.

Date

2026-09-28
