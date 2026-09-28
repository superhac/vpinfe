# Extensions

An extension adds a feature to an install without being part of VPinFE. It ships as a
directory, declares what it needs in a manifest, and is handed a context it reaches
everything through. It never receives the application.

The word is **extension** throughout. *Plugin* means a Visual Pinball standalone plugin,
which is a different thing with its own page.

## What one looks like

```
my-extension/
    extension.json
    __init__.py
    i18n/
        en.json
```

The directory name is the extension's name, and the manifest has to agree: the name
addresses it in a URL, a scope, a log namespace, a config file and the Python package
core imports, so two answers to what it is called would each be right somewhere.

`__init__.py` defines `register(ctx)`. Core calls it once at startup and never again.

Two places are searched, in this order: `extensions/` under the config directory, then the
`extensions/` the build ships. An installed extension with the same name as a bundled one
answers, and the bundled one is left alone.

```python
from fastapi import APIRouter


def register(ctx):
    router = APIRouter()

    @router.get("/rating/{game_id}")
    def rating(game_id: str) -> dict:
        return {"stars": ctx.config.get("default_stars", "0")}

    ctx.add_router(router, scope=ctx.scope("read"))
    ctx.events.subscribe("game.selected", lambda **payload: ctx.logger.debug("%s", payload))
```

## The manifest

`extension.json`, snake_case like every other JSON we write.

| key | what it is |
|---|---|
| `name` | Lowercase letters, digits and `_`, starting with a letter. Matches the directory, and is the Python package core imports - so it has to be a legal module name |
| `display_name` | A product name, shown as written in every language. Left out, it is `name` in its own `i18n/`, and then the extension's `name` |
| `version` | The extension's own version. Shown, never interpreted |
| `description` | One line, shown beside it. Left out, it is `description` in its own `i18n/` |
| `requires_platform` | The platform ABI it was built against. This build offers `1` |
| `scopes` | Core scopes it asks to use, e.g. `games:read` |
| `provides` | The actions it gates its own routes on. Core mints `ext:<name>:<action>` |
| `capabilities` | What it asks of the machine: `ui:mount`, `config:own`, `net:outbound`, `proc:spawn`, `hardware:usb`, `fs:read`, `fs:write` |
| `requires_features` | Install features it needs: `library`, `frontend`, `devices`, `overview` |
| `platforms` | `linux`, `windows`, `macos`. Empty means every one |
| `events` | Event names it publishes, without its namespace |

Everything in it is a declaration a person can be shown before installing, which is why an
unknown capability, feature or platform is refused rather than ignored: a name nobody has
heard of is not something anybody could have agreed to.

An extension whose manifest names a platform this machine is not, or a feature this
install does not have, is not loaded. It is still listed, with the reason.

## The context

`ctx` is the whole of an extension's reach. There is no way to get from it to the
application, and that is the guarantee the model rests on.

| on `ctx` | what it does |
|---|---|
| `ctx.name`, `ctx.manifest` | What this extension is and what it declared |
| `ctx.t(key, **params)` | What its own `i18n/<language>.json` says for `key`, in the language now set |
| `ctx.why(exc, at=...)` | Why something failed, in core's words, for the line under a failure. See "Its words" |
| `ctx.logger` | A logger in `vpinfe.ext.<name>` |
| `ctx.config` | `get`, `set`, `all` over its own settings |
| `ctx.events` | `subscribe` to a core event; `publish` one of its own |
| `ctx.files` | `set_roots` — the folders it works from, so core will take a path from inside one. Needs `fs:read` |
| `ctx.jobs` | `submit(kind, work)` — slow work, one at a time per kind, answerable on `/api/v1/jobs` |
| `ctx.games` | The library. `kinds`, `folder`, `folder_name_for`, `existing`, `create`, `add_table`, `put_media`, plus every operation core offers by name — `reaches()` lists them. Each needs the core scope its manifest declared |
| `ctx.apps` | `provide(...)` — add a way to play a table. `suffixes`, `plays`, `names` say what this build can play. Providing needs `apps:provide` |
| `ctx.games.launch_game(...)` | Start a game on this play host. Needs `launch:invoke`, which `games:write` does not grant |
| `ctx.scope(action)` | The scope name for one of its declared actions |
| `ctx.entries` | `contribute(key, fetch)` — add something to every entry a theme is handed; `stale(key)` - drop what core holds under it |
| `ctx.tokens` | `offer(name, contexts, value)` - a name a user may write into a command. Offered as `<extension>.<name>` |
| `ctx.catalogs` | `contribute(key, name, subject, link)` — say where a game, a table or a file is somewhere else |
| `ctx.players` | Who plays here, and the accounts it holds for them. See "Players and their accounts" |
| `ctx.ui` | `action(...)` - offer a verb for the Console to draw; `community(...)` - a list shown under Community, and `kept(key)` - its last good read; `settings(base)` and `state(base)` - say where its settings and what it is holding can be read; `account(base, ...)` - say a player can hold an account with it. All need `ui:mount` |
| `ctx.add_router(router, scope=...)` | Serve routes under `/api/v1/ext/<name>/` |

`ctx.games` is not a second implementation of the HTTP API — it calls the API's own route
functions. They are plain functions; the scope gate lives in each route's dependencies and
only fires for a request arriving over the wire, so the gate is applied here against the
manifest instead. An extension reaches the same code an HTTP client reaches, and the two
cannot drift.

That matters because they had. While the host kept its own smaller copy of the library,
the importer worked out for itself what folder a game's name would become and got it
wrong, on names core strips a character from. Anything core offers is now reachable by the
name it is offered under:

```python
found = ctx.games.list_games(q="taxi", limit=10, offset=0)
ctx.games.rate_table(game_id, table_id, 8)
ctx.games.reaches()      # what this extension may actually call
```

Launching is gated apart from the rest. It takes over the cabinet rather than editing a
record, and the scope vocabulary already said so before extensions existed: reading what
is happening is not the same as causing it to happen, and stopping a table somebody may be
mid-game on is a third permission again. So `games:write` does not grant it — an extension
that starts a game asks for `launch:invoke` by name, and whoever installs it reads it by
name.

An extension in this process cannot use the API over HTTP — a synchronous call into the
server it is running inside deadlocks — and may not import the library, so this is the
door.

It is bounded twice. The manifest's `scopes` decide which of those an extension may call
at all, which is what makes declaring them mean something. And a path it hands over has to
be inside a folder it declared through `ctx.files`, which is a tighter check than the same
one on a route: this one knows which extension is asking, where a route only knows a path.

There is deliberately no hook seam yet. A hook can stop a core operation, and handing that
out before the isolation story for it is designed would let a broken extension stop a
launch.

Routers are collected during `register` and mounted once. One added afterwards would never
be reachable, so it is refused rather than left to answer nothing.

## Its words

An extension keeps what it says in `i18n/en.json` beside its code, and a translation is the
same file under the language's name, `i18n/de.json`. What it declares is found there by
what it declared:

| key | names |
|---|---|
| `name`, `description` | The extension, where the manifest leaves them out |
| `action.<key>.label`, `action.<key>.description` | An action |
| `action.<key>.result.<field>` | A count its run reports, beside the number |
| `settings.label`, `state.label` | Its settings and what it is holding. Left out, the Console uses its own |
| `account.label` | The heading over a player's account with it. Left out, its name |
| `account.share.help` | What its account's Share switch makes of what is played, under the switch. Left out, the Console names what a played game, a rating and a high score become once claimed |
| `account.consent.<name>` | Not a key core reads by name - `consent=` on `ctx.ui.account(...)` takes already-resolved strings, and this is where an extension keeps the ones it built from |
| `community.<key>.title` | A Community list |
| `community.<key>.column.<field>.header`, `...help` | One of its columns |
| `community.<key>.view.<key>.name`, `...help` | One of its views |
| `token.<name>.says` | A name a command can use |
| `app.<id>.name`, `app.<id>.field.<key>.label`, ... | An app it provides |

Anything else is its own to ask for, `ctx.t("wizard.title")`, and `contract.words(name)`
is the same for a module that is not handed `ctx`.

A key the file does not have falls back to what the thing was declared by: an action to
its key, a column or a count to its field. A word handed over in code, `title="VPinPlay"`,
is shown as written in every language, which is for a product name.

The file is served under `ext.<name>.`, so an extension adds words and never changes one of
core's. `scripts/i18n.py` reads a bundled extension's file along with core's, and
`--record` and `--pseudo` write its hashes and pseudo-locale. The invariants hold a bundled
one's file to what its code asks for, both ways, and to the rules under "Type" in
`docs/conventions.md`, and fail on a sentence written anywhere in its code outside a
docstring, a log line, a query or a builtin exception. What a `ValueError` says reaches a
log and nobody else; what an `HTTPException` says is read by a person, so its `detail`
comes from `ctx.t`, or from `ctx.why` when it is the reason something failed.

`ctx.why(exc)` says why in the words core uses under its own failures - a missing file, a
refused permission, a host that did not answer - and in the language set. For anything
core has no words for it is the exception's own text, so the extension words that one
itself, from its own catalog. `at=` is the URL or path being reached, for an exception
that does not carry it, such as urllib's:

```python
try:
    with urllib.request.urlopen(endpoint, timeout=10) as answer:
        rows = json.load(answer)
except (urllib.error.URLError, TimeoutError) as exc:
    raise HTTPException(502, detail=ctx.why(exc, at=endpoint)) from exc   # vp.example did not answer in time
except ValueError as exc:
    raise HTTPException(502, detail=ctx.t("error.not_json")) from exc
```

A note or a row's error carries it the same way, as `{"text": ctx.t(...), "detail":
ctx.why(exc)}`. `contract.why` is the same for a module that is not handed `ctx`.

## Adding a way to play a table

VPinFE plays Visual Pinball, and through the generic app anything a person can point at a
binary. An extension is how another format becomes first-class: it claims its own
suffixes, so a library of them is worth importing rather than read and dropped.

```python
ctx.apps.provide(
    id="fp",
    name="Future Pinball",
    suffixes=(".fpt",),
    fields=({"key": "bam_path", "path": "dir"},),
    command=lambda entry, settings: ["/opt/fp", "--play", entry["table"]],
)
```

```json
{
  "app.fp.field.bam_path.label": "BAM folder",
  "app.fp.field.bam_path.description": "Where BAM is installed, if it is"
}
```

The app's words are in the extension's `i18n/en.json` under `app.<id>.`, keyed the way an
app's own file is (see "An app's words" in `docs/conventions.md`). A field that file does
not name takes core's words, so Program reads the same on every launcher. `name` is given
here because Future Pinball is a product name.

It is described in plain data because an extension cannot import the app contract — its
one door is `common.extensions.contract`, which is what makes the import boundary
checkable. `command` answers with a list of arguments, never a string: splitting one is
how a path with a space in it becomes a crash or an injection, and only the extension
knows where its own arguments end. Answering with nothing runs the launcher's configured
binary and arguments instead.

Apps this build ships are offered first, so a provided one cannot take `.vpx` out from
under Visual Pinball by loading before somebody looks. An id already in use is refused:
ids are stored in a table's record and read back long afterwards. What an extension
provides is taken back when it unloads, so a disabled extension leaves no suffix claimed
by something that is no longer there.

A provided app does not get the rest of the app contract — parsing a table, resolving a
ROM, a settings surface, a launch of its own for a recording. Those are declared absent
rather than half-answered, the same way the generic app declares them.

## Adding something to an entry

A theme reads `entry.ext.<key>`. It never learns which extension answered, and no
extension gets a method of its own on the theme surface — the alternative needs a new call
for every connector that follows.

```python
def rating_for(game):
    # game is {game_id, vps_id, name, manufacturer, year, ipdb_id} - a description,
    # never our object. Return whatever a theme should read, or None where there is
    # nothing.
    return {"stars": look_it_up(game["vps_id"])}

ctx.entries.contribute("rating", rating_for)
```

Each value in the description is the effective one: an extension sees the match a user
corrected, not the one the scan found.

**Core makes the call; the browser makes none.** `fetch` runs on core's thread when the
player moves to a game, so it may block — but it must not raise for a game it simply has
no answer about. One that raises costs its own key and nothing else.

Three things core does that no theme author sees. The answer is held per process, so one
fetch serves every window and survives a reload. The games either side are fetched on the
same signal, so what somebody sees is the answer fetched a step ago and the gap only shows
on the first game of a cold start. And the message that carries an answer names the game
it is about, so one arriving after the wheel has moved lands on the entry it belongs to.

The slot is always present and empty at library load — a list of four hundred games cannot
wait on four hundred calls to somebody else's server. A theme written as
`if (entry.ext.rating)` is correct throughout without knowing there is a waiting state.

An answer is held for the rest of the run. When what an extension knows changes - a
fresh list read, say - `ctx.entries.stale("rating")` drops what core holds under that key,
and each game is asked again the next time it is reached. Only the extension that
contributes a key can drop it.

An extension that answers from one of its own Community lists makes no call per game at
all: it holds the rows its list route last answered, and reads them back at start with
`ctx.ui.kept(key)` (below). VPinPlay's rating works that way.

## Adding an outside link

A game, a table or a file can have a page somewhere else, and an extension can say where.

```python
ctx.catalogs.contribute(key="vpinplay", name="VPinPlay", subject="game",
                        link=lambda game: f"https://www.vpinplay.com/tables?vpsid={game['vps_id']}")
```

`subject` is `game`, `table` or `file`; anything else is refused at registration. `link` is
handed a plain description of the subject and answers its address there, or "". Core draws
it as a row named for the place, with `open_in_new`. A link that raises, or answers anything
but an http or https address, is left out.

## Adding a name a command can use

A user writes commands that run when VPinFE starts and around every table. Core declares
what one of them may say — `{table}`, `{rom}`, `{launcher_bin}` — and an extension adds to
that list.

```python
def season(values):
    # values is what this context has resolved so far. Answer a string; empty is an
    # answer, and this must not raise on an install that has none.
    return ctx.config.get("season", "")

ctx.tokens.offer("season", (ctx.tokens.TABLE,), season)
```

What it stands for is `token.season.says` in the extension's `i18n/en.json`. A name with
nothing saying what it stands for is refused.

**The name carries the extension's id.** You declare `season`; a user writes
`{league.season}`. The dotted half is built from the manifest rather than spelled here,
so two extensions may offer the same idea without reaching each other — and core's own
names, which never carry a dot, can grow without reaching either. Who is playing is one of
core's: `{player}` is the initials of the one player up, and blank with several.

`contexts` says where the command runs: `ctx.tokens.VPINFE` for the pair around VPinFE
itself, `ctx.tokens.TABLE` for the pair around every table. Declare only the ones the name
means anything in. A name that is always blank costs a reader more than one that was never
offered.

`value` runs while a command is being prepared, so it has to answer quickly. One that
raises stands for nothing and is logged, and the table still launches. Pass
`after_only=True` for something only the half that runs afterwards can know.

**A name goes when its extension does.** A command still holding one is refused by that
name, the same as any name nothing declares. The alternative is a `--flag` left with
nothing after it, reading whatever came next as its value.

## Offering something to do

An extension does not draw. It declares an **action** — a verb — and core renders it, so
every action looks like the Console rather than like whoever wrote the extension, and it
keeps working if that extension later runs out of process, which a drawn page would not.

```python
ctx.ui.action("import", "/wizard")
```

```json
{
  "action.import.label": "Bring in a library",
  "action.import.description": "Convert a library from another frontend into game folders"
}
```

Two calls on the extension's own router, under `base`:

| call | answers |
|---|---|
| `GET {base}` | `title`, `help`, `fields`, `confirm` — what to ask, if anything |
| `POST {base}/check` | `ready`, `summary`, `notes`, `errors`, more `fields`, `confirm` — what would happen |
| `POST {base}/run` | `{"job_id": …}`, or the outcome directly |

**How many steps an action has is read off what it answers, never declared.** No `fields`
means press it and it happens. `fields` means fill them in first. A `confirm` means a step
showing what would happen before it runs. A declared mode would be a second statement of
what the answers already say, and the two come apart.

A run returns a `job_id` where the work is slow — core watches it on `/api/v1/jobs` — or
the outcome where it is not, with an optional `message` and `summary`. An action that is
one call and a sentence should not have to wear a progress bar.

`fields` are `{key, type, label, value, help}`. Both `check` and `run` receive
`{"values": {…}}`. The words in these answers are the extension's to look up, with `ctx.t`.

| type | asks for |
|---|---|
| `string` | a line of text |
| `path` | a file or folder on the machine core runs on, with `wants`: `dir`, `file` or `exe` |
| `select` | one of `choices` |
| `multi` | several of `choices` |
| `switch` | on or off |

`confirm` is the verb at the point of no return, and it is the action's own: a generic
"Confirm" makes every action look like every other one. `notes` travel with the summary,
because a count that stays quiet about what the job cannot do describes something that
will not happen.

A note is a string, or `{text, detail}` when there is a reason behind it. `text` is the
line and `detail` shows on hover, the way the Console shows the reason under one of its own
failures:

```json
{"text": "Settings.xml could not be read", "detail": "Nothing is at /pbx/Config/Settings.xml"}
```

`errors` refuses one field by name instead: `{field_key: …}`, drawn under that field rather
than under the whole step. Each value takes the same two forms a note does.

A job's `result` may list `rows`, and every row with an `error` is shown under what did not
come across, by its `name`. That `error` takes the same two forms.

## Adding a Community list

A list an extension holds, shown under Community. Needs `ui:mount`.

```python
ctx.ui.community("tables", "/community/tables", title="VPinPlay",
                 columns=[{"field": "name", "under": ["manufacturer", "year"]},
                          {"field": "plays", "kind": "number"}, {"field": "vps_id"}],
                 views=[{"key": "most_played", "columns": ["name", "plays"],
                         "sort": [{"field": "plays", "desc": True}], "ranks": True}],
                 relation={"field": "vps_id", "keys": "vps_entry"})
```

```json
{
  "community.tables.column.name.header": "Table",
  "community.tables.column.plays.header": "Plays",
  "community.tables.view.most_played.name": "Most Played"
}
```

`base` is one of this extension's routes answering `{"rows": [...]}`. A column's `kind` is
`text`, `number` or `date`, and the first column may name `under` - row fields drawn on the
line beneath its value, as a game's maker and year are. A view has a `key`, which its
words are found by, and names its columns and its sort. With a `relation`, core asks which
rows this library holds and makes their name a link: `keys` is `vps_entry` for a link to
the game, or `vps_release` for one to the table. It is all data: core draws the list with
the grid every other page uses, and nothing of the extension's runs in the page.

Core keeps the last good read of each list on disk. The page draws it at once, with how old
it is, and asks the route again behind it; a read that fails leaves the last good list on
screen, said to be stale. The route is asked on every visit and on Refresh, so it answers
with the whole list as it is now rather than holding a copy of its own. The rail is read
when the Console loads, so a list can still be opened after its extension is switched off
or stops; then the route is not asked at all, and in place of Refresh the page says Off, or
Stopped with the reason.

`ctx.ui.kept(key)` reads that copy back: `{"rows", "read_at"}`, or None before the first
good read. It is how an extension has its list at start, before core's first read and
whether or not the service answers.

With `tag="Weekly Challenge"` as well, the list puts that tag on what this library holds
from it: the game for a `vps_entry` relation, the table for a `vps_release` one, so a
challenge naming one build of a machine tags that build and not the others. Core reads
the list shortly after it starts and every 30 minutes after; a read that fails keeps the
last good one. The tag is the extension's - nobody can rename, merge or remove it, or put
it on by hand - and it goes when the extension stops. A tag needs a `relation`. It is
written as given in every language: it is stored on games, which makes it data.

A view with `"ranks": True` is offered as an order for a collection, named for the list's
`title` and the view's name: *VPinPlay: Most Played*. It puts this library's games in the
view's sort, one field after another, each in its own direction, and there is no reversing
it. A game the list does not rank follows in title order, so the order never drops one,
and a collection's limit fills from the ranked games first. A ranked view sorts on `number`
or `date` columns only, and its list needs a `relation`; anything else is refused at
registration. A list of ratings, a leaderboard's scores and a challenge's dates all declare
it the same way. The order is read with the tags, on the same schedule, and moves on its
own from the last good read. While the extension is stopped, a collection in its order
keeps it and shows its games in title order until it runs again.

With `about="/community/tables/about"`, the list's page also says how its source stands
and what can be done about it. Core asks `GET {about}` as the page opens and again after
each act:

```json
{"status": {"text": "Not sharing - Share is off", "to": "players"},
 "acts": [{"key": "send_now", "label": "Send Now"},
          {"key": "site", "label": "Open VPinPlay", "url": "https://www.vpinplay.com"}]}
```

`status` is one line, drawn quietly in the bar above the list, or under the reason when
the list could not be read. It is a string, or `{text, detail, to}`: `detail` shows on
hover, and `to` makes the line a link, to `players` - Frontend › Players, where each
player's accounts and their Share are - or to `settings`, this extension's own page. Those
two are the whole vocabulary, and any other `to` draws the line with no link. An empty
`status` draws nothing.

`acts` are the menu at the end of the page's title, in their order, and core adds
**Settings**, opening this extension's page, after them wherever the extension has
settings. An act is `{key, label}`, and pressing it is `POST {about}/acts/{key}`, which
answers the way an account's act does: a `message` is said, a `url` is opened in a new tab.
An act carrying a `url` of its own is a link instead, opening that address in a new tab
and marked as leaving, and the extension is never called for it. A `url` that is not
`http://` or `https://` is not drawn. Offer an act only while it can work: a Send Now with
nothing waiting is left out rather than refused.

A leaderboard names its week and when it ends, a room says whose name it posts under, a
score site says who shares with it; each links its own pages. The words are the
extension's, from `ctx.t`, and core draws all of it. While the extension is stopped
neither route is asked.

## Players and their accounts

Who plays is core's; what a service calls them is the extension's. Core keeps the roster -
the owner, the other players, the guests, who is up - and an extension holds an account for
any of them it can: a user id and key at a scores site, a name a leaderboard posts under.

`ctx.players` reads the roster as plain data, the rows `players.changed` carries: `id`,
`name`, `initials`, `owner`, `guest`, `up`, `shares_initials_with`. Reading it needs
`players:read` in the manifest's `scopes`, because names and initials are about people.

| call | answers |
|---|---|
| `roster()` | Every player: the owner, the kept players, then the guests as they joined |
| `get(player_id)` | One row, or None |
| `up()` | The rows of who the next game counts for |
| `record(player_id, game_id)` | What a player other than the owner has done with one game, as `GET /api/v1/players/{id}/record` lists it: `play_count`, `play_time_seconds`, `last_played`, `best_score`, `rating`. None for the owner, whose record is the library's and read through `ctx.games`. Read only |
| `sharing(player_id)` | Whether this player's account here is sharing |
| `account(player_id)` | Its values for this player, secrets included. Empty when they hold none |
| `set_account(player_id, values)` | Replace them. Empty values remove the account |
| `holders()` | The ids of every player holding an account here |

The first four need `players:read`; the last four are the extension's own and need
nothing declared. Values are strings, kept in the extension's own settings file under
`accounts`, keyed by player id - which is why `accounts` is not a name a setting can
take. **A guest's are held in memory and never
written**, so a visitor leaves nothing on the disk, and they go when the guest does.
Removing a player forgets their account with every extension.

**Share** is core's and the same on every account: whether this account sends what the
install records. It is off until somebody turns it on, since what a service is sent is
often public, except for a guest who joined with a card, whose account shares. Core draws
the switch; an extension reads it with `sharing` and sends nothing on its own while it is
off. Something the person asks for by hand - an act - is theirs to have asked.

`account.share_changed` says when an account's Share moves: `player`, `{id, name,
initials, owner, guest}`; `extension`, whose account it is; and `share`, what it is now.
It carries every extension's, so one reads only its own. **Turning Share off drops
whatever the account holds back to send** - games that failed to go, a queue of scores -
so nothing played while it was on goes later by hand, or when it is turned on again.

### Offering an account

```python
ctx.ui.account("/accounts", cards=("scores_site_card",), check="/available",
               consent=(ctx.t("account.consent.id"), ctx.t("account.consent.plays")))
```

Like settings, an account is declared rather than drawn: core asks the extension's own
routes under `base`, with the player's id, and draws the same panel for every extension
that offers one - a user id chosen free, claimed deliberately, then read-only. WoVP or
iScored can hold one the same way; nothing about the shape below is VPinPlay's.

| call | answers |
|---|---|
| `GET {base}/{player_id}` | `user_id`, `claimed`, `page`, `card`, `status`, `waiting`, `waiting_count`, `acts`, `fields` (unused by this shape, kept for a simpler account that is only ever settings-like) |
| `PUT {base}/{player_id}` | receives `{"values": {…}}`; saves what is given and answers as the `GET` does. Never mints a key - claiming is its own act, never a side effect of a write |
| `POST {base}/{player_id}/acts/{key}` | what came of it, with an optional `message`; `claim` and `disconnect` answer the account itself, as the `GET` does |
| `GET {base}/{player_id}/card` | `{"card": {…}, "filename"}` - the card to draw, or a `404` while there is none |
| `POST {base}/cards` | receives `{"card": {…}}`; answers `name`, `initials` and the account's `values` |
| `GET {check}?candidate=…` | `{"available": bool}` for a candidate id, asked live as one is typed. Not under `{base}/{player_id}`: it needs no player, and the Console asks it straight through to the extension, the way it asks `settings` and a Community list's `about` - `GET /ext/{extension}{check}?candidate=…`. Raise to say it could not be reached; the Console reads that as "can't reach", never as "taken" |

`user_id` is the id chosen, lower case as the service will keep it, or `""` before one is
chosen. `claimed` says whether it is registered with the service - free to change or drop
until then with a plain `PUT`, read-only after. `page` is the account's public page once
claimed, `""` before. `status` is one line in words - *1 game waiting to send*, *Sent 2
minutes ago* - or `""` while unclaimed; `waiting` is the same fact `waiting_count` puts as
a number, as a plain boolean, for a caller that has to branch on it rather than show it -
the Remote's after-a-game card, which says what became of a specific play rather than
showing the account's own sentence. An act is `{key, label, description}`; `send_now` is
the one this shape draws generically, only while claimed and something waits. `card` says
whether a card can be made for this player now. The words are the extension's, from `ctx.t`.

**Claiming is deliberate, never a side effect.** The Console's own dialog checks `check`
live as an id is typed, saves it with a plain `PUT` - nothing sent, no key made - and only
makes the key and registers the pair when the player turns Share on: an empty send (a
service's `tables: []`, read as registering the pair rather than filing one). `claim`
refuses with an ordinary error where the id was taken in the meantime, the player has no
initials, or the account already holds a key; the Console shows whatever it says and
leaves Share off. `disconnect` forgets the id and key here - the extension's own
`set_account(player_id, {})` - while the account stays with the service, whatever was
already shared.

`consent` is what Share tells the player becomes public, asked once, the first time it is
turned on: each line already in its own words from `ctx.t`, drawn as what the account
shares. Core adds that the service can neither rename nor delete an account, since this
shape never offers either.

The Console follows what an act answers. A `message` is said, and a `url` is opened in a
new tab. Core asks these in-process as whoever asked core, so the routes are gated and
fail the way any of its routes do. A route answering a `404` or an `HTTPException` is an
answer, passed on as it was given.

**A `secret` field is accepted on a write and never answered.** Answer one with its
`value` like any other field: core takes the value out of every answer from an
extension's routes, its settings included, and puts `set`, true or false, in its place.
Nothing on a page or across the network ever holds it. Leaving one empty on a write is
the extension's to decide; the Console only sends one when something was typed. This
shape's own `user_id`/key pair does not use `fields` at all - the key never crosses the
wire in either direction, only `claimed`.

### Cards

A card is a player's account as a file they can carry to another install: a QR code of
the card's text, drawn by core as an SVG, with the text also hidden in the file - in a
comment, a `<metadata>` and a `<desc>`, named for the extension:
`<!--SCORES_SITE_PAYLOAD:…-->`, `id="scores_site-payload"` and
`id="scores_site-payload-desc"`. `marker=` names them otherwise. A card is read from that
text and never from the picture.

The card an extension answers is a JSON object with a `type`, written compact with its keys
sorted. `cards=` lists the `type`s it reads: a card arriving at `POST
/api/v1/players/guests/card` goes to the extension that declared its `type`, which answers
who it is for. The guest joins up alone with the card's initials, one to three characters,
as they are, and their account shares. The same card again puts that guest up rather than
adding a second. A card used for a player's existing account, `POST
/api/v1/players/{id}/accounts/{extension}/card`, is read the same way, and the `values` it
answers are written to that account with `PUT {base}/{player_id}`.

VPinPlay's card is the one 2.x's *Download QR Code* saved, byte for byte: the same text,
the same QR settings, the same hiding places. Cards are on people's phones, so a card
from either version joins on the other, for good.

## What a game tells you

Core events say who played and who rated what, as plain lists and dicts. `game` and
`ini_config` ride along for core's own subscribers and are not part of this contract.

| event | carries |
|---|---|
| `table.launched` | `game_id`, `table_id`, `source`; `up`, who the game counts for, taken once as it starts, each `{id, name, initials, owner, guest}`; and `private`, whether the game is Private |
| `table.play_recorded` | the same, once the game has ended and its play is written, with `private` read again then; `seconds` played; `reading`, the machine's high score table as read after the game, or None; `new_entries`, `[{player, entries}]` for each player with an entry new this game |
| `game.rated` | `game_id`; `player`, whose rating it is, `{id, name, initials, owner, guest}`, or None on an install with no owner yet; and `rating`, 0 to 5, 0 meaning unrated. The owner's rating is the library's, anyone else's is in their own record |

**A Private game's data is never sent anywhere.** Not its plays, its time, its scores or
its rating, and not the fact that the library holds it - to no service, for no player,
whoever was up and whatever their Share says. A game is Private when somebody marks it so;
the events carry `private`, and a game's rows from `ctx.games` carry it too, for anything
an extension sends outside a session. An extension reads the flag and cannot set it.

A table's events - `table.launching`, `table.launched`, `table.exited` and
`table.play_recorded` - carry `source`, who started it: `frontend`, `remote`, `api`, or
`capture` for a launch that records the table's media. A recording is not a play. Nobody is
up for it, it writes no play data, and there is no `table.play_recorded` after it, so an
extension counting plays counts on that event or leaves out a `capture` launch.

```python
def on_played(**payload):
    if payload["private"]:
        return
    for credited in payload["new_entries"]:
        post_score(credited["player"]["id"], credited["entries"])

ctx.events.subscribe("table.play_recorded", on_played)
```

**A game counts for who was up; a new score goes to the player whose initials it has**, up
or not. An entry with no initials, or `???`, goes to the one player up, and with several up
to nobody. Core matches them once, so no two extensions disagree about whose a score was.
An entry is new when the table after the game holds it more times than the table before,
whatever its rank; a machine that keeps one number has a new entry when it changed. A
game with no reading before it has nothing new. `reading` is `{rom, resolved_rom,
score_kind}` with either `entries` - each `{section, rank, initials, score, ...}` - or a
single `value`.

A service that takes one player a game decides for itself what to do with several up, and
its account's status line says so rather than going quiet.

## Scopes and the gate

Core attaches the gate. An extension names an action it declared; core turns that into
`ext:<name>:<action>` and puts it on every route in the router. An extension cannot ship a
route without a gate, because it never attaches one.

A scope belonging to an extension is granted only while that extension is running.

## Config

Two homes, because there are two owners.

| file | holds |
|---|---|
| `extensions.json` | core's record of what is installed and what is switched off |
| `extension_settings/<name>.json` | that extension's own settings |

Never `vpinfe.ini` - that file holds what core is configured with, and it is where a token
would go.

A setting core used to hold for an extension is copied across once, on the first start
after that extension exists, and core stops reading it. Core keeps the old names in its
schema so a 2.x file still converts, and nothing writes them again.

A file each rather than a namespace inside one, for the same reason: a namespace in
somebody else's file is a weaker form of "own" than a file. One unreadable
`extensions.json` used to cost every extension its settings and switch the disabled ones
back on. Now one extension's bad file costs that extension.

Whether an extension is switched off stays core's record, because core has to know before
it loads anything - reading a file per extension to answer "what am I not loading" is
worse than reading one. An extension switched off is not loaded at all.

A person switches one on its card on the Console's Extensions page, or with
`PUT /api/v1/extensions/{name}/enabled`, and either writes `extensions.json`. Off is at once:
it goes the way a broken one does, below, and says it was switched off rather than that it
broke. On waits for the next start, because routes mount once and one that was off never
registered any. Until then it says it starts at the next restart.

Settings are not beside an extension's code: one the build ships has no directory in the
config dir, so they need a home that does not depend on where the code came from.

## Logs

`vpinfe.ext.<name>`, issued by the context. An extension never logs into a core namespace,
because the namespace is how "which extension did this?" stays answerable.

## When one breaks

Reading the manifest, importing the package and calling `register` are each somebody
else's code, and any of them failing costs one extension. A `register` that raises part
way loses what it had offered by then, the same as below. Afterwards, an unhandled error
out of one of its routes, or out of a handler it subscribed, takes that extension out:

- its subscriptions are dropped, so it is told nothing more
- its scopes go with it, so nothing holds a grant into something that is not running
- the apps it provided, with their words, and the services it answered go too, so no
  suffix stays claimed by it and core asks it nothing
- its routes keep their paths and answer `501` naming the extension and the reason,
  because a `404` reads as a typo

That is for the run it happened in. It is not written down: a fault that happened once
must not take an extension away until somebody notices a setting they never set.

An error an extension raises deliberately - a `NotFoundError`, an `HTTPException` - is an
answer, not a fault, and changes nothing.

## Where the code is

- `common/extensions/contract.py` - the manifest and the shape of the context. The only
  module of ours an extension imports.
- `common/extensions/context.py` - what `register(ctx)` is handed.
- `common/extensions/host.py` - loading, the registry, and the kill switch.
- `common/extensions/store.py` - `extensions.json`, and each extension's own file.
- `common/extensions/accounts.py` - where an account's values live, and the secret taken
  out of every answer.
- `common/extensions/cards.py` - drawing a card and reading one.
- `httpapi/extensions.py` - the gate, the mount, `GET /api/v1/extensions` and the switch,
  and asking an extension's route in-process.
- `httpapi/player_accounts.py` - a player's accounts, Share and cards on the wire.

`tests/fixtures/extensions/sample/` is a worked example that uses all of it.
