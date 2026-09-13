# Immich Desktop Client

A Windows background app that continuously watches local folders and mirrors their state to an Immich server: uploading new or changed media, and optionally reflecting local deletions remotely.

## Language

**Local upload record**:
The client's persistent, per-file record of what it has uploaded — remote asset id, content checksum, and provenance — consulted whenever a watched file is later modified or removed to decide what should happen remotely.
_Avoid_: shelve, dbm, database (these name past/possible storage mechanisms, not the concept).

**Own upload**:
An asset the local upload record can vouch this client itself created. Established only once, at upload time, when the server responds `status:"created"`; the server keeps nothing afterward that distinguishes this client's uploads from pre-existing duplicates, so "own upload" status cannot be reconstructed later — only recorded when it happens. A duplicate (see below) still gets a local upload record entry, mapping its path to the existing asset id so it's never re-uploaded, but that entry is never an own upload and is never eligible for any delete.
_Avoid_: our asset, uploaded asset.

**Ownership hint**:
A custom `metadata` key the client writes on every upload, readable back later via `GET /assets/{id}/metadata`. It exists solely as a recovery aid if the local upload record itself is lost or corrupted — a best-effort way to rebuild it — and is never, by itself, sufficient to authorize a delete. Distinct from own upload, which is the local upload record's own authoritative flag and the only thing that ever gates a delete.
_Avoid_: ownership marker, ownership proof (it proves nothing on its own).

**Duplicate**:
An asset a `POST /assets` call reports as already existing (`status:"duplicate"`), returning that asset's id. It may have been uploaded earlier by this client, by another client entirely, or found via an unrelated match — never assume it is an own upload without checking the local upload record.
_Avoid_: existing asset.

**Watched root**:
One of the top-level folders the client is configured to watch. It groups local upload record entries and is the unit the client checks for accessibility before a catch-up scan: if a watched root itself can't currently be reached (an unmounted drive, an unavailable network share), every entry under it is skipped for that run rather than treated as deleted. Removing a watched root from configuration leaves its local upload record entries untouched permanently — no pruning, no server action; only future watching stops.
_Avoid_: watched folder, watched directory (use when speaking generally about any folder under a root; "watched root" specifically means the configured top-level entry the availability check applies to).

**Live delete**:
A remote delete triggered immediately when the watcher observes a locally watched file disappear while the app is running.
_Avoid_: real-time delete, instant delete.

**Catch-up delete**:
A remote delete triggered instead at app startup, for a file the local upload record lists but that is absent from disk. Distinct from live delete because "file's gone" is ambiguous here between "the user deleted it" and "the drive or network share it lived on isn't currently mounted" — the app cannot tell these apart, so catch-up delete is gated by its own toggle, independent of live delete's.
_Avoid_: startup delete, sync delete.

**Replace**:
The client's response to a locally modified own upload: upload the new content, optionally `PUT /assets/copy` from the old asset to carry over its albums/favorite/stack, then trash the old asset. Never applies to an asset that isn't an own upload.
_Avoid_: update, re-upload (that term names only the raw upload step within a replace).

**Trash**:
The outcome of `DELETE /assets` without `force`: the asset is marked restorable for a server-configured retention window. This is the **only** delete outcome this client ever produces — live delete, catch-up delete, and the manual bulk delete are all trash-only, and only ever for an own upload. Force delete (`DELETE /assets {force:true}`, unrecoverable, skips trash) is a real server capability this client deliberately never invokes, for any asset, under any circumstance — see [ADR 0001](./docs/adr/0001-never-force-delete.md).
_Avoid_: soft delete (for trash), hard delete / force delete (as something this client does — it doesn't).

**Supported server**:
A server whose `GET /server/version` reports 3.0.0 or above — the sole, checked condition the client requires before it will watch or upload at all. A server below that (or one that fails to report a parseable version) is refused outright, at settings-save time and at every app startup. Distinct from a server the code merely happens to work against; only the checked threshold makes a server "supported."
_Avoid_: compatible server (implies untested/incidental, not the checked threshold).
