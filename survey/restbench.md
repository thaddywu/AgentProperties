
---

# Spotify tool surface in full

The agent's tool list is `reduce_openapi_spec(spec)` over `specs/spotify_oas.json`: every
`get/post/put/patch/delete` operation becomes one tool named `"<METHOD> <path>"`, with `$ref`s
dereferenced and docs stripped to request args + happy-path response. So the 40 rows below *are*
the tools.

## 1. Catalog (read-only, immutable, globally shared)

| Tool | Required args | Optional | Scope |
|---|---|---|---|
| `GET /search` | `q`, `type` (album,artist,playlist,track,…) | market, limit, offset, include_external | — |
| `GET /tracks/{id}` | id | market | — |
| `GET /albums/{id}` | id | market | — |
| `GET /albums/{id}/tracks` | id | market, limit, offset | — |
| `GET /artists/{id}` | id | — | — |
| `GET /artists/{id}/albums` | id | include_groups, market, limit, offset | — |
| `GET /artists/{id}/top-tracks` | id | market | — |
| `GET /artists/{id}/related-artists` | id | — | — |
| `GET /recommendations` | `seed_artists`, `seed_genres`, `seed_tracks` (all marked required) | limit, market | — |
| `GET /browse/new-releases` | — | country, limit, offset | — |

## 2. Identity

| Tool | Args | Scope |
|---|---|---|
| `GET /me` | — | `user-read-private`, `user-read-email` |

## 3. Playlists (full CRUD-ish lifecycle)

| Tool | Required | Body / optional | Scope |
|---|---|---|---|
| `POST /users/{user_id}/playlists` | user_id; body `name` | `public`, `collaborative`, `description` | `playlist-modify-public|private` |
| `GET /me/playlists` | — | limit, offset | `playlist-read-private` |
| `GET /playlists/{playlist_id}` | playlist_id | market, fields, additional_types | — |
| `PUT /playlists/{playlist_id}` | playlist_id | body `name`,`public`,`collaborative`,`description` | `playlist-modify-*` |
| `GET /playlists/{playlist_id}/tracks` | playlist_id | market, fields, limit, offset | `playlist-read-private` |
| `POST /playlists/{playlist_id}/tracks` | playlist_id | `uris` (query or body), `position` | `playlist-modify-*` |
| `DELETE /playlists/{playlist_id}/tracks` | playlist_id; body `tracks` | body `snapshot_id` | `playlist-modify-*` |

## 4. Library / social — set-membership toggles

| Tool | Required | Scope |
|---|---|---|
| `GET /me/tracks` | — (market, limit, offset) | `user-library-read` |
| `PUT /me/tracks` | `ids` | `user-library-modify` |
| `DELETE /me/tracks` | `ids` | `user-library-modify` |
| `GET /me/albums` | — | `user-library-read` |
| `PUT /me/albums` | `ids` | `user-library-modify` |
| `DELETE /me/albums` | `ids` | `user-library-modify` |
| `GET /me/following` | `type=artist` (+after, limit) | `user-follow-read` |
| `PUT /me/following` | `type` (artist|user), `ids` | `user-follow-modify` |
| `DELETE /me/following` | `type`, `ids` | `user-follow-modify` |

## 5. Player — the stateful device machine

| Tool | Required | Scope |
|---|---|---|
| `GET /me/player` | — (market, additional_types) | `user-read-playback-state` |
| `GET /me/player/devices` | — | `user-read-playback-state` |
| `GET /me/player/currently-playing` | — | `user-read-currently-playing` |
| `PUT /me/player/play` | body `context_uri` \| `uris`, `offset`, `position_ms` (all optional ⇒ resume) | `user-modify-playback-state` |
| `PUT /me/player/pause` | — | `user-modify-playback-state` |
| `POST /me/player/next` | — | `user-modify-playback-state` |
| `POST /me/player/previous` | — | `user-modify-playback-state` |
| `GET /me/player/queue` | — | `user-read-playback-state` |
| `POST /me/player/queue` | `uri` (+`device_id`) | `user-modify-playback-state` |
| `PUT /me/player/repeat` | `state` ∈ {track, context, off} | `user-modify-playback-state` |
| `PUT /me/player/volume` | `volume_percent` ∈ [0,100] | `user-modify-playback-state` |

## 6. Derived history views (read-only, lagging)

| Tool | Required | Scope |
|---|---|---|
| `GET /me/top/{type}` | type ∈ {artists, tracks}; time_range ∈ {short,medium,long_term} | `user-top-read` |
| `GET /me/player/recently-played` | — (limit, after, before) | `user-read-recently-played` |

---

# Resources and their lifecycles

Five resource kinds, with sharply different lifecycle shapes. This is the part that matters for
writing temporal properties.

### A. Catalog objects — `track`, `album`, `artist` (immutable, no lifecycle)

Never created or destroyed by the agent. Their only role is to **produce ids**. The important
property is *id provenance*: no `{id}` may appear in a call unless it was returned by an earlier
response. The only ways to obtain a first id without one are:

```
GET /search  |  GET /browse/new-releases  |  GET /me/*  (top, tracks, albums, following, playlists, player)
```

Everything else is id-consuming. Containment gives the traversal edges:
`artist → /artists/{id}/albums → album → /albums/{id}/tracks → track`.

### B. Playlist — the only create/mutate resource, and it is **create-only**

```
        POST /users/{user_id}/playlists          (needs user_id ← GET /me)
   ∅ ─────────────────────────────────────►  EXISTS(empty)
                                                 │  ▲
             PUT /playlists/{id}  (rename/描述/public)│  │
             POST /playlists/{id}/tracks  (+items) │  │
             DELETE /playlists/{id}/tracks (−items)│  │
                                                 ▼  │
                                              EXISTS(n items)

        ✗ no DELETE /playlists/{id}  — a playlist can never be destroyed
```

Notable lifecycle facts:

- **Create-before-use.** `playlist_id` is only obtainable from `POST /users/{uid}/playlists` (the
  create response) or from `GET /me/playlists`. This is the one genuine happens-before edge in
  the whole benchmark, and it is 3 links long: `GET /me` → `POST …/playlists` → `POST …/tracks`.
- **No deletion.** The real Web API deletes playlists via "unfollow playlist", which this spec does
  not expose. So playlist creation is **monotone and irreversible** — every failed/retried
  "make me a playlist" task leaves garbage behind. That's why `init_spotify.py` has to nuke the
  account between runs.
- **Optimistic concurrency.** `DELETE /playlists/{id}/tracks` accepts `snapshot_id`; every mutation
  returns a new one. A correct agent that removes items should carry the snapshot from its most
  recent read — a stale snapshot is a detectable ordering violation.
- **Ordered container.** `POST …/tracks` takes `position`; item removal is by uri+positions. So
  playlist contents are a *list*, not a set — order-sensitive post-conditions are possible.

### C. Library membership — `saved tracks`, `saved albums`, `followed artists/users`

A set per (user, kind), with an idempotent two-state toggle per element:

```
   NOT_SAVED  ──PUT /me/tracks?ids=X──►  SAVED  ──DELETE /me/tracks?ids=X──►  NOT_SAVED
      (PUT when already SAVED = no-op; DELETE when absent = no-op)
```

Same shape for `/me/albums` and `/me/following?type=artist|user`. Properties: idempotent,
commutative across distinct ids, self-inverse. There is **no "is X saved" check endpoint** in this
spec (the real API's `/me/tracks/contains` is absent), so the only way to test membership is to
page `GET /me/tracks` — a read that the agent usually skips, which makes "unfollow X" tasks
silently succeed even when X was never followed.

### D. Player — session state machine, not a document

This is the only resource with **preconditions that can make a call fail on a well-formed request**.

```
        no active device ──(user opens Spotify app)──► device active
                                                          │
                          PUT /me/player/play ────────────┤
                                 ▼                        │
                            ┌─ PLAYING ─┐                 │
   PUT /me/player/pause ────┤           ├──── POST next / previous  (moves cursor within context)
                            └─ PAUSED  ─┘
        orthogonal state:  volume ∈ [0,100]     repeat ∈ {off, track, context}
        side channel:      queue  (POST /me/player/queue appends; GET reads)
```

Preconditions the spec implies but never states as a rule:

- every player op requires an **active device**; `GET /me/player` returns `204 No Content` when
  there is none, and writes return `404 NO_ACTIVE_DEVICE`. Hence `GET /me/player/devices` is a
  legitimate probe step that the gold paths mostly omit.
- `pause` on an already-paused player → `403 Restriction violated`; likewise `next` with no context.
- `volume` requires a device that supports volume (`supports_volume` in the device object).
- **Gap in this spec**: `device_id` exists only on `POST /me/player/queue`. `play/pause/next/
  previous/volume/repeat` take no `device_id`, and `PUT /me/player` (transfer playback) is missing
  entirely. So the agent can *enumerate* devices but cannot *target* one — device selection is
  implicit, out-of-band state.
- Player writes are **not idempotent in effect** (`next` twice ≠ `next` once) — unlike the library
  toggles. That's the sharpest correctness distinction in the whole tool set.

### E. Derived views — `top items`, `recently played`

Read-only projections of listening history. Not writable, eventually consistent, and they change as
a *side effect* of player writes. Any evaluation that reads them after a play action is inherently
flaky; `GET /me/top/{type}` appears in 3 gold paths purely as a retrieval source.

---

## Spec bugs found while reading

- `PUT /me/tracks`: `requestBody.required = ["uris"]` but the only declared property is `ids`.
- `DELETE /me/albums`, `PUT /me/albums`, `DELETE /me/tracks`, `PUT|DELETE /me/following`: `ids` is
  declared **both** as a required query param and as a body property — the caller can satisfy the
  schema two different ways, and RestGPT's prompt ("GET ⇒ params, PUT/POST ⇒ data") pushes it to
  the body-only form, which the real API accepts but which makes the two paths non-equivalent for
  trace matching.
- `GET /recommendations` marks all three `seed_*` params required; the real API requires at least
  one of them. An agent obeying the doc would have to invent artist+genre+track seeds.
- `POST /playlists/{id}/tracks` accepts `uris` in query *or* body — same dual-encoding problem.
