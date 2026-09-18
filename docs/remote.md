# Remote

A phone-shaped surface for driving an install from across the room: what is playing, pick something else, and control it with a thumb. It is served by the Console process at `/remote` and is a separate shell from the Console, not a narrow rendering of it.

The Console at `/console` is desk-first and organized as a workbench, a grid beside an inspector. That shape does not fit one hand, so `/remote` is its own page with its own layout and the same palette, tokens and API client.

## The three screens

`console/remote.py` defines them in `SCREENS`, and `?screen=` links to one directly.

- **Now** - what is playing, on which target, how long, plus any running job and anything wanting attention. Quit table. When nothing is playing it shows the last game played with its rating control.
- **Play** - a search field, collection as a select, and a row that opens a sheet whose primary button is Launch. A row does not launch on tap.
- **Control** - a mode bar and a held D-pad over the input seam: select, back, the three overlays, quit.

## Targets

The target picker sits in the header on every screen, because every action's meaning depends on which install it is aimed at. It is not drawn when only one device is registered.

Changing the target re-reads everything below the header. The library has to come from the target as well as the commands, since a list read from this install offers ids the target has never heard of.

A target is shown as reachable by asking it, not by reading `last_reachable`. A device recorded a moment ago carries a fresh timestamp whether or not it is switched on.

The row for the machine serving the page is decided by the data rather than by comparing install ids: an install records itself with no address, and every other row is written from an address it was heard at.

## What it can write

Rating, favorite, and add-to-collection. Everything else is read, launch, or control.

Add-to-collection offers manual collections only. `GET /collections` already carries `type`, derived from whether the collection has criteria. With no manual collections the action is shown disabled with the reason rather than hidden.

## Routes it uses

Every one of these already existed for the Console and the API; Remote adds none.

| Job | Route |
|---|---|
| What is playing, quit | `GET /play/state`, `POST /play/stop` |
| Launch | `POST /games/{id}/launch` |
| Search, collections | `GET /games`, `GET /collections` |
| Lifecycle actions | `GET`/`POST /actions` |
| Jobs, live | `GET /jobs`, `GET /events` |
| Targets | `GET /devices`, `POST /devices/probe` |
| Rate, favorite | `PUT /games/{id}/rating`, `/favorite` |
| Add to collection | `PUT /collections/{name}/games/{game_id}` |

`GET /actions` returns `available` and `reason` per action. Remote greys a button and shows that sentence rather than deciding for itself what is possible.

## Where it lives

```
console/page.py      Console shell, /console
console/remote.py    Remote shell, /remote
console/api.py       shared client
console/data.py      shared reads
console/theme.py     shared tokens
console/panel.py     shared fact list
```

Two shells in one package. The shared modules are not extracted to a neutral home; see `docs/conventions.md` on the panel being a shape rather than a place.

`reconnect_timeout` is set on the route, at 300. A phone locking its screen is the most common disconnect this surface sees.

## Density

Density is a per-surface token in `console/theme.py`, not a second stylesheet. `--target-min` is the Console's 32px floor and is raised to 44px where the pointer is a finger; `--star-size` is sized on its own, because five 44px boxes is a row 220px wide.

Palette and treatment stay shared. A second stylesheet is how one product starts looking like two.

## `/remote` is not `/mobile`

They are unrelated and the names suggest otherwise.

- `/remote` is this surface: a phone driving an install.
- `/mobile` means VPX Mobile, a phone we send tables **to**. `KIND_VPX_MOBILE` and the `mobile` config section mean the same thing.

Nothing about this surface uses the word "mobile".
