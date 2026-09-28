# D002 Photos stay on disk

Context

The library is large. Putting the pictures in git would make the repo unusable.

Decision

Sorted photos live in Photos/YYYY/MM-Month/. Photos, the takeout zips, the databases, the thumbnails, and the model weights stay out of git. The repo holds source only.

Consequences

A clone has no pictures. This drive is the library. Losing the drive loses the photos, the face names, and the captions.

Date

2026-09-28
