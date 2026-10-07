# Analysis cache

`ssmdconvert report` stores versioned JSON analysis snapshots and reusable
per-chapter preparation results in the user cache. Snapshots include the selected
source/chapter fingerprints, effective analysis options, generic preparation
results, SSMD mapping records, report data, and TXT projection metadata. Records
are checksummed and validated before reuse. The cache is local derived data, not
part of an SSMD document or book bundle.

## Location

- If `XDG_CACHE_HOME` is set: `$XDG_CACHE_HOME/ssmdconvert`
- Windows: `%LOCALAPPDATA%\Cache\ssmdconvert`
- Other platforms: `~/.cache/ssmdconvert`

There is no cache-path CLI override. The cache uses separate `chapters/`,
`analyses/`, and `index/` records beneath that root. A source index retains only a
bounded history of recent analysis IDs.

## Reuse and freshness

Each `report` run recomputes SSMD-specific analysis and saves a source-level
snapshot. Compatible per-chapter preparation results are reused by default.
`ssmdconvert report SOURCE --refresh` bypasses cached per-chapter preparation and
reruns preparation for the selected sections before saving a fresh snapshot.
Re-running identical inputs may produce the same deterministic analysis ID.

`ssmdconvert context SOURCE CHANGE_ID` resolves a generic change ID from that
source's saved analyses and verifies only the current bytes of the affected
chapter. If those bytes differ from the cached chapter fingerprint, context fails
as stale and recommends refreshing the report. Changes to unrelated chapters do
not invalidate the requested context. Missing analyses are not silently
recomputed by `context`; first run `report`, then retry.

## Removing or sharing cache data

To clear the cache, stop `ssmdconvert` and remove the `ssmdconvert` directory
under the location above. A later report recreates it. There is no command that
clears the cache automatically.

Cache files can contain source and prepared unit text used to render context, as
well as SSMD-derived data and fingerprints. Treat them as sensitive local data;
review a requested `context --bug-report` payload before sharing it. Deleting the
cache does not modify source SSMD, workspaces, or bundles.
