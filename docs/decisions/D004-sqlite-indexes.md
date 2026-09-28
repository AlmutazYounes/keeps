# D004 Indexes are sqlite files

Context

Faces, captions, job progress, and review scores have to survive a restart. The photo server should read them without loading the models.

Decision

Each index is a sqlite file with WAL, created on first use. gallery/faces/faces.sqlite stores people, face boxes, and embeddings. gallery/captions/captions.sqlite stores the caption and the file time. gallery/jobs/jobs.sqlite stores whether a job is running. gallery/dispose/dispose.sqlite stores sharpness and color spread for review. _sort_state.sqlite stores takeout progress.

Consequences

A restart continues from the saved rows. The databases stay on this drive and are not in git. Two writers share a file through WAL and a busy timeout.

Date

2026-09-28
