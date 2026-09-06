# Kiosk changelog

## 2026-09-05 — Vision investigation corrections

- Replaced one-second wall-clock track eviction with missed-frame retention and tolerant box association.
- Added track lifecycle events and lifetime, recreation and loss telemetry.
- Added reduced-resolution detection with native-coordinate overlays; embedding remains on the original camera frame.
- Removed temporary-file recognition and the duplicate detection pass.
- Cached valid active embeddings for each configured recognition session.
- Changed local matching to an explicit Euclidean distance threshold and separated display score from probability.
- Added detector, quality, embedding and search metrics for developer mode.
- Stopped rendering missing recognition values as 0%.
- Restricted landmarks, Track ID and confidence details to developer mode.
- Added tracker and local matcher regression tests and documented the database/gallery audit.
- Corrected the JSON gallery/probe boundary to pass NumPy arrays into `face_distance`, preventing repeated realtime `list - list` processing failures.
