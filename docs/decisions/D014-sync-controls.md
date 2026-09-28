# D014 Settings controls each sync

Context

Face recognition and descriptions started with the gallery. Settings could show the counts, and a restart was the only way to pick the work up again.

Decision

Each card can pause, continue, or rewrite. Pause stops that job and a later start leaves it paused. Continue runs only the photos that are not saved yet. Rewrite deletes that job's saved rows and runs the model again. A face rewrite also deletes people and the names typed for them. Descriptions lose their sentences until the model writes them again.

Consequences

A paused description run stays paused across a gallery restart. Continue is what starts it. Rewrite is the way to apply a different model to photos that were already saved.

Date

2026-09-28
