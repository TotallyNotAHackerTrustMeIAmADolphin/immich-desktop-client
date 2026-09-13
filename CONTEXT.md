# Immich Desktop Client

A Windows background app that continuously watches local folders and mirrors their state to an Immich server: uploading new or changed media, and optionally reflecting local deletions remotely.

## Language

**Local upload record**:
The client's persistent, per-file record of what it has uploaded — remote asset id, content checksum, and provenance — consulted whenever a watched file is later modified or removed to decide what should happen remotely.
_Avoid_: shelve, dbm, database (these name past/possible storage mechanisms, not the concept).

**Own upload**:
An asset the local upload record can vouch this client itself created. Established only once, at upload time, when the server responds `status:"created"`; the server keeps nothing afterward that distinguishes this client's uploads from pre-existing duplicates, so "own upload" status cannot be reconstructed later — only recorded when it happens.
_Avoid_: our asset, uploaded asset.

**Duplicate**:
An asset a `POST /assets` call reports as already existing (`status:"duplicate"`), returning that asset's id. It may have been uploaded earlier by this client, by another client entirely, or found via an unrelated match — never assume it is an own upload without checking the local upload record.
_Avoid_: existing asset.

**Live delete**:
A remote delete triggered immediately when the watcher observes a locally watched file disappear while the app is running.
_Avoid_: real-time delete, instant delete.

**Catch-up delete**:
A remote delete triggered instead at app startup, for a file the local upload record lists but that is absent from disk. Distinct from live delete because "file's gone" is ambiguous here between "the user deleted it" and "the drive or network share it lived on isn't currently mounted" — the app cannot tell these apart, so catch-up delete is gated by its own toggle, independent of live delete's.
_Avoid_: startup delete, sync delete.

**Replace**:
The client's response to a locally modified own upload: upload the new content, optionally `PUT /assets/copy` from the old asset to carry over its albums/favorite/stack, then trash the old asset. Never applies to an asset that isn't an own upload.
_Avoid_: update, re-upload (that term names only the raw upload step within a replace).

**Trash** / **Force delete**:
Two distinct outcomes of `DELETE /assets`. Trash (the default, no `force`) marks the asset restorable for a server-configured retention window. Force delete skips trash and is unrecoverable. The client must never force-delete anything but an own upload it can positively identify via the local upload record.
_Avoid_: soft delete / hard delete.

**Supported server**:
A server whose `GET /server/version` reports 3.0.0 or above — the sole, checked condition the client requires before it will watch or upload at all. A server below that (or one that fails to report a parseable version) is refused outright, at settings-save time and at every app startup. Distinct from a server the code merely happens to work against; only the checked threshold makes a server "supported."
_Avoid_: compatible server (implies untested/incidental, not the checked threshold).
