# Remote

A phone-shaped surface for driving an install from across the room: what is playing, pick something else, and control it with a thumb. It is served by the Console process at `/remote` and is a separate shell from the Console, not a narrow rendering of it.

The Console at `/console` is desk-first and organized as a workbench, a grid beside an inspector. That shape does not fit one hand, so `/remote` is its own page with its own layout and the same palette, tokens and API client.

## Who is holding this

Players are per install, not per phone, so the Remote asks who is holding it before it writes anything on anybody's behalf.

A phone can say who it is, remembered per browser and per target in `console/remembered.py` - a phone aimed at two installs can answer differently on each:

- **Nobody said** (the ordinary case, and the owner's own phone never has to do anything else): the phone behaves exactly as it always has. A rating goes to the library, Favorite is offered, adding to a collection is offered.
- **A kept player**, chosen with **This Is Me** on the identity sheet (the person icon in the header): a rating goes to their own record instead of the library's, Favorite is not offered - it is the owner's alone - and adding to a collection still is, since collections are the household's. **Not Me** clears it.
- **A guest**, set by Join: the same as a kept player, and adding to a collection is not offered either, since a guest is gone at shutdown. **Sign Out** removes them.

The header names the target on every screen; a kept player's initials sit beside it. A guest's does not - "not shown" here is not security, since anyone can say they are anybody on an unauthenticated LAN surface, but it keeps a visitor's screen about them without dressing up a claim nobody can back with a key.

### Join

Reached from the cabinet's second QR (`/remote?screen=join`) or from the identity sheet's own way in for a phone already on the page. Two choices, under both the one line said once - *you're a guest here until VPinFE closes*:

- **Use My Card** picks a file and reads the text 2.x's Download QR Code hid inside it - never the QR picture, so there is no decoder and no PNG to carry. A card's account already shares; joining puts the guest up alone.
- **Just Initials** - three letters, no account, up alone. A guest who wants to share afterwards types a user id from the identity sheet, which makes them a key the same way the Console's Players page does; **Save Card** then downloads what core draws for it, the same file the Console's Save Card would.

### On Now

Who is up is a switch per player, shown only with more than one player in the roster - the same gate the cabinet's own Player menu uses. A kept player who has not yet put themselves up gets **I'm Up** alone rather than the whole roster; once they are up, or if they were already, they see the same switches everyone else does. A guest only ever sees their own.

The idle card - *Last played*, with a rating - is superseded the moment a play is recorded this session: the result card then shows, for whichever of who was up belongs on this phone (everyone for nobody said or the owner, theirs first for a kept player, theirs alone for a guest), the game, their new high score entry where they made one, and what each of their sharing accounts did with it - *Sent to {service}*, *Waiting to send*, or *Not sent: {service} takes one player per game* where more than one player was up and this was not the one credited. The phone's own row carries the rating control.

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
- A switch or a wheel move at the screen reaches the phone over the target's event stream. Each open page follows `frontend.state_changed`, `play.state_changed`, `capture.run_changed`, `players.changed` and `table.play_recorded` on a thread of its own, because a read that waits for the next event would otherwise hold the Console's event loop. The thread stops when the page goes. Who is up and the result card live on this same thread, tied to the frontend the way everything else here is - a target too old to report its frontend follows none of these either.
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

Rating, favorite, and add-to-collection; starting, pausing and stopping a recording, and deciding what one kept; who is up, joining and leaving, and a guest's own account. Everything else is read, launch, or control.

Add-to-collection offers manual collections only. `GET /collections` already carries `type`, derived from whether the collection has criteria. With no manual collections the action is shown disabled with the reason rather than hidden.

A rating always goes to the library for the owner and to a player's own record for anyone else, never the other way round. Favorite and add-to-collection follow who is holding the phone the way [Who is holding this](#who-is-holding-this) describes.

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
| What the frontend shows | `GET /frontend/state`, and `GET /events?events=frontend.state_changed,play.state_changed,capture.run_changed,players.changed,table.play_recorded` |
| Switch the frontend, move the wheel | `PUT /frontend/collection`, `PUT /frontend/game` |
| Targets | `GET /devices`, `POST /devices/probe` |
| Rate, favorite | `PUT /games/{id}/rating`, `/favorite` |
| Add to collection | `PUT /collections/{name}/games/{game_id}` |
| The roster, who is up | `GET /players`, `PUT /players/{id}/up` |
| Join with a card, or with initials | `POST /players/guests/card`, `POST /players/guests` |
| Sign out, or leave a kept player's identity | `DELETE /players/{id}` (Not Me is local - it forgets nothing on the target) |
| A player's rating of a game | `PUT /players/{id}/ratings/{game_id}` |
| A player's record, for the rating shown while browsing | `GET /players/{id}/record` |
| A guest's accounts, for the identity sheet | `GET /players/{id}/accounts` |
| Share with an account, Save Card | `PUT /players/{id}/accounts/{ext}`, `/share`, `GET .../card` |

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
