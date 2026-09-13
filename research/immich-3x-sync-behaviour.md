# Immich 3.x behaviour a folder-sync client must handle

Research for wayfinder ticket #3 (map #1). Target: Immich **v3.1.0**.
Sources: Immich source code and OpenAPI spec at tag `v3.1.0`, compared against older tags (`v2.0.0` … `v2.7.5`, `v3.0.0`), plus the release notes and PR descriptions. No blog summaries were used.
The driver's server (192.168.0.61) was probed only with an unauthenticated `GET /api/server/version`. It returned `{"major":3,"minor":1,"patch":0}`.

Short link bases used below:
- `S` = https://github.com/immich-app/immich/blob/v3.1.0/server/src
- `SPEC` = https://github.com/immich-app/immich/blob/v3.1.0/open-api/immich-openapi-specs.json
- `CLI` = https://github.com/immich-app/immich/blob/v3.1.0/packages/cli/src/commands/asset.ts

---

## 1. `POST /assets`: required fields, formats and duplicate response

**Answer**

- **Request.** It is `multipart/form-data`.
  - Required: `assetData` (the file), `fileCreatedAt` and `fileModifiedAt`.
  - Optional: `filename`, `duration` (integer milliseconds), `isFavorite` (`"true"`/`"false"`), `visibility`, `livePhotoVideoId`, `metadata` (a JSON-string array of `{key, value:object}`) and `sidecarData` (an XMP file).
  - Optional header: `x-immich-checksum`, a SHA-1 in hex, or base64 if the value is 28 characters long.
- **Dates.** Both date fields must be ISO-8601 datetimes **with `Z` or a `±HH:MM` offset**. The rules:
  - Seconds and fractional seconds are optional.
  - A value with no timezone is rejected with a 400.
  - A space instead of `T` is also rejected.
  - The current client sends `str(datetime.fromtimestamp(mtime))`, e.g. `2024-05-01 12:34:56.789`. That fails on both counts.
  - Fix: `datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()` or `.astimezone().isoformat()`.
- **Device fields.** `deviceId` and `deviceAssetId` no longer exist. PR 27818 removed them and migration `DropDeviceIdAndDeviceAssetId` dropped the columns, so the old values are gone and were not moved anywhere. The DTO is a plain `z.object` (zod's default is to strip unknown keys), and `server/src` has no `.strict()`/`strictObject`. Sending the fields is therefore silently ignored.
- **Response.** A new upload returns `201 {id, status:"created"}`. A duplicate returns `200 {id, status:"duplicate"}`, where `id` is **the existing asset's id**. A duplicate is detected at two points:
  1. Before the file is processed: `AssetUploadInterceptor` looks up `x-immich-checksum`.
  2. After the file is stored: the unique index on `(ownerId, checksum) WHERE libraryId IS NULL` is violated, and the handler re-queries by checksum.
- **Duplicate scope.** Both lookups filter only on `ownerId`, `checksum` and `libraryId IS NULL`. They do **not** filter on `deletedAt` or `status`, which has two consequences:
  - **A trashed asset still counts as a duplicate.** Re-uploading a file whose asset is in the trash returns `duplicate` with the trashed asset's id, and the asset stays trashed. See §3 and §5.
  - Assets from other users and from external libraries are never returned as duplicates.
- **Errors.** Validation errors now look like `{"message":"Validation failed","errors":[{code,path,message}]}` (PR 28204, v3.0.0) instead of `message: string[]`.

**Can the client tell that it did not upload an asset? (server data only)**

**No, not after the fact.**
- The `status` field of the upload response is the only reliable signal, and it exists only at upload time. `created` means this request made the asset. `duplicate` means it already existed, whether uploaded by this client earlier, by the mobile app, the web UI or another tool.
- The client must record where each asset came from at that moment.
- Nothing stored on the server tells the two cases apart:
  - `ownerId` is the same user.
  - `libraryId` is `null` for every uploaded asset.
  - `checksum` is identical by definition.
  - `AssetResponseDto` in v3 has no device or client field.
  - `createdAt` (upload time) only proves "not created by this request".
- **Possible durable marker (heuristic).**
  - How it works: send `metadata=[{"key":"immich-desktop-client","value":{...}}]` on upload. Metadata is written only when the asset is created, not for a duplicate, and can be read back with `GET /assets/{id}/metadata`.
  - Limits: any API user can write the same key (`PUT /assets/{id}/metadata`), and custom keys only work on ≥ v2.5.0 (earlier versions accept only `mobile-app`). Treat it as a hint, never as permission to force-delete.

**Evidence**
- DTO: `S/dtos/asset-media.dto.ts` (`AssetMediaBaseSchema`, `AssetMediaCreateSchema`). Response: `S/dtos/asset-media-response.dto.ts`.
- Date codec with `offset: true`: `S/validation.ts#L138-L152`. The spec regex requires `(?:Z|[+-]HH:MM)` (`SPEC`, `components.schemas.AssetMediaCreateDto.properties.fileCreatedAt`). In the spec, `required: [assetData, fileCreatedAt, fileModifiedAt]`.
- Controller sets 200 for duplicates: `S/controllers/asset-media.controller.ts` (`uploadAsset`).
- Service: `S/services/asset-media.service.ts` (`uploadAsset` catch block with `isAssetChecksumConstraint`). Interceptor: `S/middleware/asset-upload.interceptor.ts`.
- Queries: `S/repositories/asset.repository.ts#L664-L685`. Unique indexes: `S/schema/tables/asset.table.ts#L31-L42`. Checksum parsing: `S/utils/request.ts#L4-L6`.
- `AssetResponseDto` without device fields: `S/dtos/asset-response.dto.ts#L61-L117`. Column drop: `S/schema/migrations/1776263790468-DropDeviceIdAndDeviceAssetId.ts`.
- PR https://github.com/immich-app/immich/pull/27818 (also removed `/assets/exists` and `/assets/device/:deviceId`). PR https://github.com/immich-app/immich/pull/28204.
- Metadata key: `z.string()` in `S/dtos/asset.dto.ts#L102-L107`. The `AssetMetadataKey` enum is no longer referenced. In v2.0.0–v2.4.x the key was `ValidateEnum(AssetMetadataKey)`.

**Confidence:** high for the request shape, duplicate semantics and the "no server-side provenance" conclusion. Medium for the metadata-marker idea, which is not exercised end to end.

---

## 2. Replacing a locally modified file (`PUT /assets/{id}/original` is gone)

**Answer**

- **Removal.** `PUT /assets/{id}/original` (replaceAsset) was removed in v3.0.0 (PR 27022). The PR text says "use `copyAsset` (`POST /assets/copy`)", but **the code and the spec say `PUT /assets/copy`**. It returns `204 No Content`, has operationId `copyAsset`, and needs API-key permission `asset.copy` plus access to both assets. It is not in the v3 PUT→PATCH deprecation list.
- **Body:** `{sourceId, targetId, albums?, sharedLinks?, stack?, favorite?, sidecar?}`. Every flag defaults to `true`. The call is rejected if either asset is missing or the two ids are equal.
- **What it copies from source to target (nothing else):**
  - album memberships
  - shared-link memberships
  - stack (joins the source's stack, or merges it into the target's)
  - `isFavorite`
  - the XMP sidecar file (copied to `<target originalPath>.xmp`, then metadata re-extraction is queued)
- **What it does not copy:** tags, people/faces, manual edits to description, date, location or rating, visibility (archive/locked), edits (crop/rotate), custom asset metadata, activity/comments, memories, and the asset id itself. Anything that referenced the old id keeps pointing at the old asset.
- **It does not delete the source.**
- **Resulting replace flow:**
  1. `POST /assets` with the new file. Changed content means a new checksum, so this normally returns `created`.
  2. Optionally, `PUT /assets/copy {sourceId: old, targetId: new}`.
  3. `DELETE /assets {ids:[old]}` without `force`, i.e. move it to trash.

  **"Upload as new + trash old" is the sane baseline.** `copy` is an optional middle step. It only adds album, favorite, stack and shared-link preservation. For a sync client that adds assets to its own album anyway, the main gain is keeping *other* albums and the favourite flag.
- **Edge cases:**
  - If the modified file's content matches an existing asset (a revert, or a copy of another file), step 1 returns `duplicate` with that asset's id, which may be trashed. Do not trash "old" if it is the same id.
  - Only call copy/delete for assets this client itself created. See §1 and §3.
- **Versions:** `PUT /assets/copy` first appears in **v2.2.0** (PR 23172, "feat: asset copy", merged 2025-10-29). It is absent in v2.0.0–v2.1.x. Replace existed up to v2.7.x.

**Evidence**
- `S/controllers/asset.controller.ts` (`@Put('copy')`, `@HttpCode(204)`). `S/dtos/asset.dto.ts#L154-L164`. `S/services/asset.service.ts#L183-L271` (`copy`, `copyStack`, `copySidecar`).
- `SPEC` paths: `/assets/copy` → `put` only. `/assets/{id}/original` → `get` only.
- PR https://github.com/immich-app/immich/pull/27022 (text says POST; the code is PUT). PR https://github.com/immich-app/immich/pull/23172.

**Confidence:** high for the method and what is or isn't copied. Medium that upload + copy + trash leaves the timeline and albums looking right to a user (**verify in integration test**).

---

## 3. `DELETE /assets`: trash vs `force`, retention, restore

**Answer**

- **Request:** `DELETE /assets` with JSON `{ids: uuid[], force?: boolean}`. Returns `204` and needs permission `asset.delete`.
- **`force` omitted or `false`:**
  - Sets `status=trashed` and `deletedAt=now`.
  - Restorable via `POST /trash/restore/assets {ids}` → `200 {count}` (only rows still `trashed`), `POST /trash/restore` (all) or `POST /trash/empty`.
- **`force: true`:**
  - Sets `status=deleted` and emits `AssetDeleteAll`, which immediately queues `AssetEmptyTrash`. That job queues `AssetDelete` for every `deleted` row, removing the DB row and files on disk.
  - **Skips the trash and cannot be restored.** The restore queries filter `status = trashed`.
- **Retention:**
  - Server config `trash.enabled` defaults to `true` and `trash.days` to `30`.
  - The nightly `AssetDeleteCheck` job permanently deletes assets with `deletedAt <= now - days`. When trash is disabled, `days` counts as 0, so trashed assets are purged on the next nightly run.
  - The DELETE endpoint itself ignores the trash setting.
  - The client cannot read `trash.days` with a normal API key (admin config). Assume "restorable for an unknown, admin-configured period, possibly 0".
- **Safety:**
  - Deleting an id that `POST /assets` returned as `duplicate` deletes the **user's pre-existing asset**, which applies to the old client's force-delete as well.
  - Since duplicates include trashed assets, a file whose asset was trashed and is uploaded again resolves to the trashed id. Detect this with `bulk-upload-check`'s `isTrashed` and restore it, instead of assuming it is live.
- **Unchanged since:** the same logic is in v2.0.0 (`deleteAll`), and the `/trash/*` routes exist in v2.0.0.

**Evidence**
- `S/controllers/asset.controller.ts` (`@Delete()`). `S/dtos/asset.dto.ts#L56-L58`. `S/services/asset.service.ts#L379-L391` (`deleteAll`), `#L273-L307` (`handleAssetDeletionCheck`).
- `S/controllers/trash.controller.ts`. `S/services/trash.service.ts`. `S/repositories/trash.repository.ts` (restore/restoreAll filter `status = Trashed`).
- Defaults: `S/config.ts#L403-L406`.

**Confidence:** high. Medium on the exact timing of permanent deletion after `force` (a job queue); **verify in integration test** whether a re-upload of the same bytes right after a force delete returns `duplicate` with the doomed id.

---

## 4. Albums: find an owned album by name, add assets, response shape

**Answer**

- **Finding the album.** Use `GET /albums?isOwned=true&name=<exact name>`:
  - `name` is an exact, case-sensitive SQL `=` on `albumName`. It orders by `createdAt desc` and skips deleted albums.
  - Booleans must be the literal strings `true`/`false` (`z.stringbool`, case-sensitive).
  - Other parameters: `id`, `isShared` (renamed from `shared`) and `assetId`. `assetId` ignores the others.
  - Changed in v3.0.0 (PR 28213): **with no parameters the endpoint returns owned *and* shared-with-me albums.** The current client's unfiltered `GET /albums` + name match can pick someone else's album.
- **Names are not unique.** The client should store the chosen album id and pick deterministically if there are several.
- **Response:** `AlbumResponseDto[]` with `id`, `albumName`, `description`, `albumUsers`, `shared`, `hasSharedLink`, `assetCount`, `albumThumbnailAssetId`, `createdAt`, `updatedAt`, `startDate`, `endDate`, `lastModifiedAssetTimestamp`, `isActivityEnabled`, `order`, `contributorCounts`.
  - **No `ownerId` in v3.** It was present in v2.x. PR 27467 moved ownership into `album_user`.
  - `albumUsers` has at least one entry. "First entry is always the album owner."
- **Create:** `POST /albums {albumName, description?, assetIds?, albumUsers?}` → `AlbumResponseDto`. The new id is **`id`**; the current client reads `['asset_id']`, which is a bug.
- **Add assets:** `PUT /albums/{id}/assets {ids: uuid[]}` → `200 BulkIdResponseDto[]`, one entry per id: `{id, success, error?: duplicate|no_permission|not_found|unknown|validation, errorMessage?}`.
  - An asset already in the album gives `success:false, error:"duplicate"`, not an HTTP error.
  - Needs permission `albumAsset.create` on the album and asset-share access to each asset.
  - Not deprecated in v3.
  - Bulk alternative: `PUT /albums/assets {albumIds, assetIds}` → `{success, error?}`.
- **On 2.x:** the global `ValidationPipe({transform:true, whitelist:true})` has no `forbidNonWhitelisted`, so `isOwned`/`name` are silently dropped. The v2 default (no `shared`) already returns **owned albums only**. Sending `isOwned=true&name=…` and **also filtering by `albumName` on the client** gives the right result on 2.x and 3.x.

**Evidence**
- `S/controllers/album.controller.ts`. `S/dtos/album.dto.ts#L34-L79` (Create/AddAssets/GetAlbums), `#L109-L142` (`AlbumResponseSchema`).
- `S/repositories/album.repository.ts#L186-L225`. `S/services/album.service.ts` (`getAll`, `addAssets`). `S/utils/asset.util.ts#L33-L71`. `S/dtos/asset-ids.response.dto.ts`. `S/validation.ts` (`stringToBool`).
- `SPEC` `/albums` get params: `assetId, id, isOwned, isShared, name`.
- PR https://github.com/immich-app/immich/pull/28213 and PR https://github.com/immich-app/immich/pull/27467.
- v2.7.5 behaviour: `server/src/services/album.service.ts` (`getOwned` default) and `server/src/app.module.ts#L46` at tag v2.7.5.

**Confidence:** high.

---

## 5. Avoiding re-hashing and re-uploading: `bulk-upload-check` and checksum header

**Answer**

- **Bulk check:** `POST /assets/bulk-upload-check {assets: [{id: <client key, e.g. path>, checksum: <sha1 hex or base64>}]}` → `200 {results: [{id, action: "accept"|"reject", reason?: "duplicate"|"unsupported-format", assetId?, isTrashed?}]}`.
  - It matches by `ownerId` + checksum only and includes trashed assets (`isTrashed:true`).
  - Unlike `POST /assets`, it does **not** filter `libraryId IS NULL`. An external-library asset with the same bytes is reported as `reject/duplicate`, even though an upload would still be accepted (`S/repositories/asset.repository.ts#L664-L671`).
  - Needs permission `asset.upload`.
  - The server never returns `unsupported-format` here; only `duplicate` appears in the code.
  - There is no server-side limit on the array size in the DTO. The CLI sends 5000 per request.
- **Checksum header:** `x-immich-checksum` on `POST /assets` gives the same deduplication before the file is processed. The server answers `200 duplicate` straight from the interceptor. Whether the client can skip sending the body depends on the HTTP client, since `requests` streams the whole body; `bulk-upload-check` avoids that.
- **Not on offer:** a server-side hash of a local file (hashing is always client-side SHA-1 of the whole file), or a "by device/path" lookup (`/assets/exists` and `/assets/device/:id` were removed in v3.0.0).
- **Avoiding re-hashing:** this is purely client-side. Cache `(path, size, mtime) → sha1`, then call `bulk-upload-check` with the cached hashes.

**Evidence:** `S/controllers/asset-media.controller.ts` (`checkBulkUpload`). `S/services/asset-media.service.ts` (`bulkUploadCheck`). `S/dtos/asset-media.dto.ts` and `S/dtos/asset-media-response.dto.ts`. `S/middleware/asset-upload.interceptor.ts`. `CLI` (`checkForDuplicates`). PR https://github.com/immich-app/immich/pull/27818.

**Confidence:** high.

---

## 6. Oldest server version that accepts each call in the new client's shape

The table uses tag-by-tag diffs of controllers and DTOs.

| Call (shape) | Oldest version that accepts it | Notes |
|---|---|---|
| `GET /server/version` (unauthenticated) | v1.x | Use it to branch on version. |
| `POST /auth/validateToken` | v1.x; still in 3.1.0 | Current client's connection test. |
| `POST /assets` multipart **without** `deviceId`/`deviceAssetId` | **v3.0.0** | v1.106–v2.7.x require both (`@IsNotEmpty @IsString`), so they return 400. |
| `POST /assets` **with** `deviceId`/`deviceAssetId` (any non-empty strings) | v1.106.0 (first `asset-media.controller` with `@Post()` on the assets route); accepted through 3.1.0 | 3.x strips the fields. **Sending them is harmless and keeps 2.x working.** |
| ISO-8601 dates with `Z`/offset | all of the above | v2.x `ValidateDate` uses class-validator `isDateString`, so offsets were always accepted. **2.x would not reject ISO-offset dates.** It is only 3.x that rejects the *naive* format. |
| `metadata` form field with a custom key | v2.5.0 | v1.140–v2.4.x: enum `mobile-app` only (other keys → 400). Leave it out to stay compatible further back. |
| `x-immich-checksum` header, `POST /assets/bulk-upload-check` | ≤ v1.106 (marked "added v1") | Unchanged shape. |
| `PUT /assets/copy` | **v2.2.0** | Absent in v2.0.0–v2.1.x (404). |
| `DELETE /assets {ids, force}` | ≤ v2.0.0 (identical logic) | |
| `POST /trash/restore/assets {ids}` | ≤ v2.0.0 | |
| `GET /albums?isOwned=true&name=X` | filters honoured from **v3.0.0** | On 2.x params are silently dropped, but the default is owned-only, so a client-side name filter still gives the right album. |
| `POST /albums`, `PUT /albums/{id}/assets {ids}` | ≤ v2.0.0 | Response uses `id`. v3 `AlbumResponseDto` lacks `ownerId`. |

**Takeaways:**
- A client that sends dummy `deviceId`/`deviceAssetId`, ISO-offset dates, no custom `metadata` key and no `/assets/copy` should work on **v2.0.0 through v3.1.0**.
- Using `/assets/copy` raises the floor to **v2.2.0**.
- Dropping the device fields raises it to **v3.0.0**.
- The support floor itself is a map decision.

**Evidence:**
- `git show <tag>:server/src/dtos/asset-media.dto.ts` for v1.130.0 … v3.0.0 (deviceAssetId present through v2.7.x, gone in v3.0.0).
- `server/src/controllers/asset.controller.ts` (`copy` absent in v2.1.0, present in v2.2.0).
- `server/src/dtos/album.dto.ts` (`isOwned`/`name` first in v3.0.0).
- v2.7.5 `server/src/validation.ts#L236-L256` (`ValidateDate` → `isDateString`).
- v2.7.5 `server/src/app.module.ts#L46` (whitelist, no forbid).
- v2.0.0–v2.4.0 `server/src/dtos/asset.dto.ts` (`ValidateEnum(AssetMetadataKey)`).
- v3.0.0 release notes, breaking changes: https://github.com/immich-app/immich/releases/tag/v3.0.0. v2.0.0 notes contain no API changes: https://github.com/immich-app/immich/releases/tag/v2.0.0.

**Confidence:** high for v2.0.0+ rows. Medium for exact v1.x floors (only spot-checked).

---

## 7. What the official CLI `upload --watch` does (v3.1.0)

**Worth mirroring:**
- **Watcher.** Uses chokidar with `ignoreInitial`, `awaitWriteFinish: true` (don't upload half-written files) and `alwaysStat`. It listens to `add` **and** `change` events. Depth is 1 unless `--recursive`. Watcher errors are logged, not fatal.
- **Extension filter.** Built from `GET /server/media-types` (image + video lists) and matched against the **lower-cased** extension. This fixes the "uppercase extensions ignored" bug.
- **Batching.** Queues paths and flushes every 100 paths or after a 10 s debounce, de-duplicating paths.
- **Initial scan.** A full crawl is batched separately; the watcher does not replay existing files.
- **Duplicate check.** Hashes SHA-1 locally, then calls `bulk-upload-check` in batches of 5000 and only uploads `accept` results. Hashing, checking and uploading each retry up to 3 times.
- **Upload form.**
  - Fields: `fileCreatedAt` = `fileModifiedAt` = `mtime.toISOString()` (UTC `Z`), `isFavorite=false`, optional `visibility` (new in v3.1.0, PR 29614), plus `sidecarData` if `photo.xmp` or `photo.ext.xmp` exists.
  - No device fields and no checksum header.
  - Treats both 200 and 201 as success.
- **Albums.** Duplicates are added to the album too (same as new uploads). Missing albums are created, then assets are added with `PUT /albums/{id}/assets` in chunks.

**Not worth mirroring (gaps or bugs in the CLI):**
- It resolves albums with `getAllAlbums({})`, which on 3.x includes shared-with-me albums. It never passes `isOwned`.
- It ignores `isTrashed` on duplicates, so trashed matches are silently skipped.
- On `change` it uploads the new content as a new asset and leaves the old one. There is no replace or trash logic and no server-side delete propagation. `--delete` only deletes *local* files.
- It keeps no local state; everything is rediscovered via hashes.

**Evidence:** `CLI` (`startWatch`, `checkForDuplicates`, `uploadFile`, `findSidecar`, `updateAlbums`). PR https://github.com/immich-app/immich/pull/29614.

**Confidence:** high for what the CLI does.

---

## Unverified / verify in integration test

1. Upload + `PUT /assets/copy` + trash old: check that album, favourite and timeline look right to a user, and how face/tag loss shows up.
2. Re-uploading the same bytes immediately after `DELETE {force:true}`: whether the response is `duplicate` with the soon-deleted id (race with `AssetEmptyTrash`).
3. Re-uploading a file whose asset is trashed: confirm `200 duplicate` with the trashed id and that the asset stays trashed until `POST /trash/restore/assets`.
4. Confirm `deviceId`/`deviceAssetId` in multipart are stripped without error on 3.1.0, as `z.object` default-strip implies.
5. The `metadata` upload field with a custom key on 3.1.0: that it persists, is readable via `GET /assets/{id}/metadata`, and has no side effects on mobile sync.
6. The Python `requests` client with `x-immich-checksum`: whether the early `200 duplicate` avoids sending the whole body, or just wastes bandwidth.
7. Exact v1.x version floors for `POST /assets` and `bulk-upload-check` (only spot-checked at v1.105/v1.106).
8. API-key permissions needed end to end: `asset.upload`, `asset.read`, `asset.delete`, `asset.copy`, `album.read`, `album.create`, `albumAsset.create`, and `asset.update` if metadata is written later. Check that a key limited to these works.
