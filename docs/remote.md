# Remote

A phone-shaped surface for driving an install from across the room: what is playing, pick something else, and control it with a thumb. It is served by the Console process at `/remote` and is a separate shell from the Console, not a narrow rendering of it.

The Console at `/console` is desk-first and organized as a workbench, a grid beside an inspector. That shape does not fit one hand, so `/remote` is its own page with its own layout and the same palette, tokens and API client.

## The three screens

`console/remote.py` defines them in `SCREENS`, and `?screen=` links to one directly.

- **Now** - what is playing, on which target, how long, plus any running job and anything wanting attention. Quit table. When nothing is playing it shows the last game played with its rating control.
  While a table is played, and not recorded, it carries **Take Picture**, and **Back** while the table is paused. Each is a tap of the input action of that name, which the frontend hands to core during play, so a player holding a phone takes a picture with no button bound. The card reads Paused while the table is.
  While a recording run goes, Now shows it in place of what is playing: the game in hand, how far the run has come, **Pause** and **Stop**. A paused run shows why, with **Resume** and **Stop**. Control shows the same card while a recording's table is up.
  With recordings waiting for a decision and no run going, Now says how many, with **Review** (see [Reviewing recordings](#reviewing-recordings)).
- **Play** - a search field, collection as a select, and the games in it. With the frontend up, a tap moves the wheel to that game, and a tap on the game already there opens its sheet. With no frontend to move, a tap opens the sheet. The sheet's primary button is Launch. A row does not launch on tap.
  Where the target records, the sheet carries **Record Media** above Launch, with **Missing Only** and **Replace**, and a line under the game's name saying what it lacks: *No Playfield Video or DMD Video*. A kind the target cannot record for that game is left out of both, such as a DMD that Visual Pinball showed no window for when the game was last recorded there. Replace keeps each recording for a decision rather than deleting what it would replace. Where the target cannot record, Record Media is dimmed with the reason under it.
- **Control** - a mode bar and a held D-pad over the input seam: select, back, the three overlays, quit.

## Following the frontend

While the target's frontend is up, the phone and the screen show the same collection and the same game.

- The Remote opens on the collection the frontend is showing, and a collection picked on the phone switches the frontend.
- A switch or a wheel move at the screen reaches the phone over the target's event stream. Each open page follows `frontend.state_changed`, `play.state_changed` and `capture.run_changed` on a thread of its own, because a read that waits for the next event would otherwise hold the Console's event loop. The thread stops when the page goes.
- The game on the wheel sits under the header on every screen, with Launch. It is not drawn while a table is up.
- With the frontend closed, Now says so and draws no Take Picture, and Control draws no pad. A press goes to the frontend's windows and nowhere else, so with none up every button would report success and nothing would hear it.
- A target too old to report its frontend answers `GET /frontend/state` with 404. The Remote then follows nothing and behaves as it did before.

A tap moves the wheel and waits for the frontend to say it moved, rather than marking the row at once. A theme that does not act on the move leaves the phone showing what the screen shows.

## Reviewing recordings

A recording kept for a decision is best judged where it will play, so Review plays it on the frontend, on the screen it belongs to, and the phone is the controller. It shows the game, the kind and how far through it is, with **Before** and **After** (the file there now, and the recording), **Use This**, **Discard**, **Skip** and **Stop**. Nothing asks for confirmation: the choice is made watching the file itself.

- Recordings go a game at a time, and each game's window by window.
- Skip leaves a recording waiting; Stop ends the frontend's preview and leaves the rest waiting.
- A recording decided at the frontend itself moves the phone on, and Before and After turned there are turned on the phone.
- The review ends where a table is launched or the frontend closes.

## Targets

The target picker sits in the header on every screen, because every action's meaning depends on which install it is aimed at. It is not drawn when only one device is registered.

Changing the target re-reads everything below the header. The library has to come from the target as well as the commands, since a list read from this install offers ids the target has never heard of. Writes go there too: a rating, a favorite or an add to a collection lands on the install the phone is aimed at.

A target is shown as reachable by asking it, not by reading `last_reachable`. A device recorded a moment ago carries a fresh timestamp whether or not it is switched on.

The row for the machine serving the page is decided by the data rather than by comparing install ids: an install records itself with no address, and every other row is written from an address it was heard at.

## What it can write

Rating, favorite, and add-to-collection; starting, pausing and stopping a recording, and deciding what one kept. Everything else is read, launch, or control.

Add-to-collection offers manual collections only. `GET /collections` already carries `type`, derived from whether the collection has criteria. With no manual collections the action is shown disabled with the reason rather than hidden.

## Routes it uses

Every one of these already existed for the Console and the API; Remote adds none.

| Job | Route |
|---|---|
| What is playing, quit | `GET /play/state`, `POST /play/stop` |
| Launch | `POST /games/{id}/launch` |
| Search, collections | `GET /games`, `GET /collections` |
| Lifecycle actions | `GET`/`POST /actions` |
| Control's buttons, Take Picture and Back | `POST /input/actions` |
| Jobs, live | `GET /jobs`, `GET /events` |
| Whether the target records | `GET /api/v1` (its `capture` capability) |
| Record Media, and what a game lacks | `POST /capture/runs`, `POST /capture/plan` |
| A run, live | `GET /capture/runs/current`, and `capture.run_changed` on the stream below |
| Pause, Resume, Stop | `POST /capture/runs/current/pause`, `.../resume`, `.../stop` |
| Recordings waiting, and deciding one | `GET /capture/proposals`, `POST /capture/proposals/{id}` |
| Play one on the frontend | `PUT`/`DELETE /frontend/preview` |
| What the frontend shows | `GET /frontend/state`, and `GET /events?events=frontend.state_changed,play.state_changed,capture.run_changed` |
| Switch the frontend, move the wheel | `PUT /frontend/collection`, `PUT /frontend/game` |
| Targets | `GET /devices`, `POST /devices/probe` |
| Rate, favorite | `PUT /games/{id}/rating`, `/favorite` |
| Add to collection | `PUT /collections/{name}/games/{game_id}` |

`GET /actions` returns `available` and `reason` per action. Remote greys a button and shows that sentence rather than deciding for itself what is possible.

## Where it lives

```
console/page.py      Console shell, /console
console/remote.py    Remote shell, /remote
console/remote_record.py  its part in recording media
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
