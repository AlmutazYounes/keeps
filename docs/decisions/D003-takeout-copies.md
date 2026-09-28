# D003 Takeout import copies files

Context

Google Takeout arrives as zip files. The same photo can sit in several albums. The date is in the metadata, the file name, or the file.

Decision

sort_photos.py reads takeout-*.zip in the repo root and copies each photo into Photos/. Album copies are kept once. Dates come from the Takeout metadata, then the file name, then the file. The script does not edit photo bytes. It stops when the disk has less than 20 GiB free. Progress is stored in _sort_state.sqlite. A file placed straight into Photos/ is picked up by restarting the gallery.

Consequences

The bytes in the zip stay as Google sent them. A second album does not create a second file. Import needs 20 GiB free. A loose file needs a server restart.

Date

2026-09-28
