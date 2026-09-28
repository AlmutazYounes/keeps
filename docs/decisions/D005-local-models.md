# D005 Faces and captions are local models

Context

The Faces page and search need names and descriptions. Sending each photo to an API would move the library off this drive.

Decision

Faces use 10g_bnkps.onnx and arcface_w600k_r50_batch.onnx. Captions use Florence-2 from onnx-community/Florence-2-base-ft. Both jobs read still photos only. A person in fewer than 10 photos stays off the Faces page. The same name on two groups merges them. A restart skips a still photo whose saved file time still matches.

Consequences

The weights have to be downloaded by hand. Videos can be searched by file name. They do not get a new face row or a new caption. A small cluster stays hidden until it reaches 10 photos.

Date

2026-09-28
