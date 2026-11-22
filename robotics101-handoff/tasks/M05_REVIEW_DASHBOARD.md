# M05 — review UX and approvals

## Implement
- Next.js episode list, video playback, timestamped scene preview, transcript, QA findings and source links.
- Reviewer notes and regenerate-scene action; scene versions and dependency invalidation.
- Preview of candidate final MP4; approval/rejection request authenticated by server; record reviewer and exact artifact SHA-256.
- Invalidate approval if candidate changes; test concurrent revision vs approval race.
- Readable stage-level logs and cost breakdown per episode.

## Acceptance
Reviewer can request scene 7 revision without rerendering scenes 1–6, 8–12, then see recomposed video, and approve it. Publication blocked on any hash mismatch.
