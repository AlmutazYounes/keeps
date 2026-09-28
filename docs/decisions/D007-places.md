# D007 Place names come from the file

Context

The map should show where a photo was taken. A city guessed from a caption would put photos in the wrong town.

Decision

Coordinates are read from the file. The city name is a Nominatim lookup, cached under gallery/cache/. A photo with no coordinates is not given a place. A lookup that returns no name does not invent one.

Consequences

The first view of a new spot needs the network. Later views use the cache. A photo with no location stays off the map. The cache is local and is not in git.

Date

2026-09-28
