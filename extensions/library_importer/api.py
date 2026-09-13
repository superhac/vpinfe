"""What the importer offers over the API.

Every route is gated on a scope this extension declared; core attaches the gate. Reading
a source is a read, and pointing at a different one is a write - saying where an install
will read from is the decision worth being a separate permission from looking at what is
there.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from . import adopt, emulationstation, pinballx, popper
from . import plan as plan_for

# Asked in order, first to claim a folder wins. PinballX is looked for first
# because it is the source somebody converting a pinball library actually has.
READERS = (pinballx, popper, emulationstation)

# Where the source is, in this extension's own settings. Not a core setting: it is a
# fact about somebody's old machine, and it has no meaning to anything else here.
SOURCE_KEY = "source_root"

# The order the questions come in. Which of them get asked depends on what is found, but
# never on how somebody arrived: going Back and forward again asks the same things in
# the same order rather than jumping over what is already answered.
STEPS = ("source", "sources", "existing", "summary")


def _after(step: str) -> tuple[str, ...]:
    """The steps still to come after the one being left."""
    at = STEPS.index(step) if step in STEPS else 0
    return STEPS[at + 1:] or (STEPS[-1],)


def reader_for(root: Path):
    """The reader that claims a folder, or None. First to claim it wins, and readers are
    asked in the order they are declared."""
    return next((one for one in READERS if one.detect(root)), None)


def _state(ctx) -> dict:
    configured = ctx.config.get(SOURCE_KEY, "")
    if not configured:
        return {"path": "", "reachable": False, "source_id": "", "source_name": "",
                "reason": "No source has been chosen"}
    path = Path(configured)
    if not path.is_dir():
        return {"path": configured, "reachable": False, "source_id": "",
                "source_name": "", "reason": "That folder is not reachable from here"}
    reader = reader_for(path)
    if reader is None:
        return {"path": configured, "reachable": True, "source_id": "",
                "source_name": "",
                "reason": "Nothing this build can read is in that folder"}
    return {"path": configured, "reachable": True, "source_id": reader.SOURCE_ID,
            "source_name": reader.SOURCE_NAME, "reason": ""}


def _preview(library) -> dict:
    """What was found, counted. The whole library would be megabytes and nobody reads a
    thousand rows to decide whether to go ahead."""
    systems = []
    for system in library.systems:
        with_media = sum(1 for game in system.games if game.media)
        with_table = sum(1 for game in system.games if game.table_file)
        matched = sum(1 for game in system.games if game.vps_id)
        systems.append({
            "name": system.name,
            "games": len(system.games),
            "with_artwork": with_media,
            "with_a_game_file": with_table,
            "already_matched": matched,
            "tables_dir": system.tables_dir,
            "enabled": system.enabled,
        })
    return {"source_id": library.source_id, "root": library.root,
            "systems": systems, "notes": list(library.notes)}


def build(ctx) -> None:
    """Register the routes, and keep what core may read in step with the setting."""
    def follow_the_setting(*extra: str) -> None:
        """Tell core every folder this import will actually read from.

        The install folder is not enough and assuming it was cost a whole run: a
        frontend keeps its database and artwork under its own roof, but the tables sit
        wherever the emulator was installed - a real PinballY library recorded them two
        directories away, and core refused all 581 of them because the importer had
        resolved the path and never declared it.

        So the roots follow what was resolved, not what was configured. Anything the
        plan points at is a folder this will open, and core cannot know that from the
        source root alone.
        """
        configured = ctx.config.get(SOURCE_KEY, "")
        wanted = [configured] if configured else []
        wanted += [one for one in extra if one]
        ctx.files.set_roots(wanted)

    def declare_roots(library, values) -> None:
        """Tell core where this import will read, before anything tries to read there.

        Before the plan, not after it: the plan counts what travels with each table,
        which means opening the tables folder, which core refuses until it has been told
        about it. The source map is derived from the library alone, so it is available
        first and does not need the plan that needs it.
        """
        found = plan_for.derive_sources(library, _chosen(values))
        follow_the_setting(*[source.path for source in found if source.active])

    follow_the_setting()

    reading = APIRouter()

    @reading.get("/source")
    def source() -> dict:
        """Where this install is set to import from, and what is there."""
        return _state(ctx)

    @reading.get("/preview")
    def preview() -> dict:
        """What a scan of the chosen source found. Reads it, writes nothing."""
        state = _state(ctx)
        if not state["source_id"]:
            return {"source_id": "", "root": state["path"], "systems": [],
                    "notes": [state["reason"]]}
        reader = next(one for one in READERS if one.SOURCE_ID == state["source_id"])
        return _preview(reader.read(Path(state["path"])))

    writing = APIRouter()

    @writing.put("/source")
    def set_source(body: dict) -> dict:
        """Point at a folder.

        Its own permission, and not because it writes a setting: core reads files under
        this folder while it is set, so choosing it is the moment somebody widens what
        this install will open. Looking at what is already there is not the same act.
        """
        wanted = str(body.get("path") or "").strip()
        ctx.config.set(SOURCE_KEY, wanted)
        follow_the_setting()
        return _state(ctx)

    @reading.get("/wizard")
    def wizard_form() -> dict:
        """Step one: what are you importing from, and where is it.

        The kind is asked rather than only sniffed. Somebody knows what they have, and a
        detector that is wrong leaves them arguing with a guess; offering "work it out"
        as the default means the common case is still one press.
        """
        state = _state(ctx)
        return {
            "step": "source",
            "title": "Bring in a library from another frontend",
            "help": "Point at the folder the other frontend keeps its library in. "
                    "Nothing there is written to or moved.",
            "fields": [
                {"key": "source_type", "type": "select", "label": "Coming from",
                 "value": "auto",
                 "choices": [["auto", "Work it out"]]
                            + [[one.SOURCE_ID, one.SOURCE_NAME] for one in READERS],
                 "help": "Which frontend the library belongs to."},
                {"key": "path", "type": "path", "label": "Install folder",
                 "value": state["path"],
                 "help": "Its database and its artwork are read from here."},
            ],
        }

    def _reader_for(values: dict, path: Path):
        """The reader this source is to be read with.

        What somebody chose, where they chose; otherwise the first that claims the
        folder. A chosen reader that does not claim it is still used - being told "that
        is not a Popper install" is more useful than quietly reading it as something
        else.
        """
        wanted = str(values.get("source_type") or "auto").strip()
        if wanted and wanted != "auto":
            return next((one for one in READERS if one.SOURCE_ID == wanted), None)
        return reader_for(path)

    @writing.post("/wizard/check")
    def wizard_check(body: dict) -> dict:
        """Whatever comes next: another question, or what it all adds up to."""
        values = body.get("values") or {}
        leaving = str(body.get("step") or "source")
        wanted = str(values.get("path") or "").strip()
        if not wanted:
            return _again("Say where the library is.", values)

        ctx.config.set(SOURCE_KEY, wanted)
        follow_the_setting()
        path = Path(wanted)
        if not path.is_dir():
            return _again("That folder is not reachable from here.", values)
        reader = _reader_for(values, path)
        if reader is None:
            return _again("Nothing this build can read is in that folder.", values)
        if not reader.detect(path):
            return _again(f"That does not look like {reader.SOURCE_NAME}.", values)

        library = reader.read(path, ctx.apps.plays, ctx.apps.names())
        declare_roots(library, values)
        made = plan_for.build(library, ctx.games.existing(), _chosen(values),
                              str(values.get("on_existing")
                                  or plan_for.DEFAULT_ON_EXISTING),
                              _systems(values), ctx.games.folder_name_for,
                              library.source_id, ctx.games.kinds(),
                              ctx.games.companions_of)

        for step in _after(leaving):
            if step == "sources":
                return _sources_step(reader, library, made)
            if step == "existing" and made.already:
                return _existing_step(made)
            if step == "summary":
                return _summary_step(reader, library, made)
        return _summary_step(reader, library, made)

    def _again(reason: str, values: dict) -> dict:
        found = wizard_form()
        found["notes"] = [reason]
        for field in found["fields"]:
            if field["key"] in values:
                field["value"] = values[field["key"]]
        return found

    def _systems(values: dict) -> list[str]:
        """Which of the source's systems, or all of them where it was never asked."""
        return [str(one) for one in (values.get("systems") or [])]

    def _chosen(values: dict) -> dict | None:
        held = {key: values[key] for key, *_rest in plan_for.SOURCES if key in values}
        return held or None

    def _sources_step(reader, library, made) -> dict:
        fields = [{
            "key": source.key, "type": "path", "label": source.label,
            "value": source.path,
            "help": source.help + (" Worked out from the source."
                                   if source.derived else ""),
        } for source in made.sources]

        # Only where there is a choice to make. One system is not a decision, and a
        # control with a single option in it is a question that answers itself.
        systems = [one.name for one in library.systems if one.games]
        if len(systems) > 1:
            fields.insert(0, {
                "key": "systems", "type": "multi", "label": "Systems",
                "value": systems,
                "choices": [[one, one] for one in systems],
                "help": "Which of the source's systems to bring across.",
            })

        return {
            "step": "sources",
            "title": f"Reading it as {reader.SOURCE_NAME}",
            "help": "Where each kind of thing lives. What could be worked out is filled "
                    "in; anything left empty is not imported.",
            "fields": fields,
        }

    def _existing_step(made) -> dict:
        return {
            "step": "existing",
            "title": f"{len(made.already)} of these are already here",
            "help": "From a previous run, or added another way. Matched by the folder "
                    "this import would make, then by catalog id, so one you have "
                    "renamed is not brought in twice.",
            "fields": [{
                "key": "on_existing", "type": "select", "label": "What to do",
                "value": made.on_existing,
                "choices": [list(one) for one in plan_for.ON_EXISTING],
            }],
            "notes": [one.folder for one in made.already[:8]]
                     + ([f"and {len(made.already) - 8} more"]
                        if len(made.already) > 8 else []),
        }

    def _summary_step(reader, library, made) -> dict:
        """Everything the previous steps decided, and what it comes to."""
        found = _preview(library)
        counts = plan_for.expected(made)
        going = len(made.matches) if made.on_existing == "fill" else len(made.new)

        rows = [["Reads as", reader.SOURCE_NAME], ["Folder", library.root]]
        rows += [[source.label if source.active else f"No {source.label.lower()}",
                  source.path or "not being imported"]
                 for source in made.sources]
        if made.already:
            rows.append(["Already here",
                         f"{len(made.already)} - "
                         f"{dict(plan_for.ON_EXISTING)[made.on_existing].lower()}"])
        rows.append(["Going into", "the location new games go to"])
        rows.append(["What comes across"])
        rows += [[label, str(counts[key])] for key, label in plan_for.COUNTS]

        return {
            "step": "summary",
            "title": "This is what will happen",
            "ready": bool(going),
            "reason": "" if going else "Nothing left to bring in",
            "summary": rows,
            "notes": found["notes"],
            "confirm": f"Bring in {going} game{'' if going == 1 else 's'}",
        }

    @writing.post("/wizard/run", status_code=202)
    def start_import(body: dict) -> dict:
        """Convert the chosen source into game folders. Answers with a job.

        A job because it is slow and because it is the shape everything slow here takes:
        an import of six hundred games is minutes of copying, and a request that waited
        for it would time out somewhere in the middle with no way to ask what happened.
        Progress and the outcome are on /api/v1/jobs, the same as a library scan.
        """
        values = body.get("values") or {}
        path = Path(str(values.get("path") or "").strip())
        reader = _reader_for(values, path) if path.is_dir() else None
        if reader is None:
            return {"started": False,
                    "reason": "Nothing this build can read is in that folder"}
        systems = _systems(values)
        location = str(body.get("location") or "")

        def work(job):
            library = reader.read(path, ctx.apps.plays, ctx.apps.names())
            declare_roots(library, values)
            job.log(f"Read {len(library.games)} games from {library.root}")
            made = plan_for.build(library, ctx.games.existing(), _chosen(values),
                                  str(values.get("on_existing")
                                      or plan_for.DEFAULT_ON_EXISTING), systems,
                                  ctx.games.folder_name_for, library.source_id,
                                  ctx.games.kinds(), ctx.games.companions_of)
            want = plan_for.expected(made)
            report = adopt.run(ctx, library, systems, location, made)
            # Counted again from the plan the run was handed, so the report says what
            # was asked for beside what happened rather than what was hoped for.
            report["against"] = plan_for.against(want, report)
            report["expected"] = want
            job.log(f"Created {report['games']}, failed {report['failed']}")
            return report

        job = ctx.jobs.submit("import", work)
        return {"started": True, "job_id": job.id,
                "links": {"job": f"/api/v1/jobs/{job.id}"}}

    ctx.ui.action(key="import", label="Bring in a library",
                  description="Convert a library from another frontend into game "
                              "folders.", base="/wizard")
    ctx.add_router(reading, scope=ctx.scope("read"))
    ctx.add_router(writing, scope=ctx.scope("write"))
