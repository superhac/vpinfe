import sys
import os
import platform
import logging
from pathlib import Path
from screeninfo import get_monitors
from common.table import Table
import json
import time
import subprocess
from common.tableparser import TableParser
from common.vpxcollections import VPXCollections
from common.tablelistfilters import TableListFilters
from common.dof_service import start_dof_service_if_enabled, stop_dof_service
from common.launcher import (
    build_vpx_launch_command,
    get_effective_launcher,
    parse_launch_env_overrides,
    resolve_launch_tableini_override,
)
from common.metaconfig import MetaConfig
from common.score_parser import read_rom, result_to_jsonable
from platformdirs import user_config_dir


logger = logging.getLogger("vpinfe.frontend.api")


class API:
    def __init__(self, iniConfig, window_name=None, ws_bridge=None, frontend_browser=None):
        self._iniConfig = iniConfig
        self.window_name = window_name          # 'bg', 'dmd', or 'table'
        self.ws_bridge = ws_bridge              # WebSocketBridge instance
        self.frontend_browser = frontend_browser  # ChromiumManager instance
        self.allTables = TableParser(self._iniConfig.config['Settings']['tablerootdir'], self._iniConfig).getAllTables()
        self.filteredTables = self.allTables
        self.jsTableDictData = None
        # Track current filter state
        self.current_filters = {
            'letter': None,
            'theme': None,
            'type': None,
            'manufacturer': None,
            'year': None,
            'rating': None,
            'rating_or_higher': False,
        }
        # Track current sort state
        self.current_sort = 'Alpha'
        # Track current collection
        self.current_collection = None
        # Check for startup collection
        startup_collection = self._iniConfig.config['Settings'].get('startup_collection', '').strip()
        if startup_collection:
            try:
                self.set_tables_by_collection(startup_collection)
            except Exception:
                logger.exception("Could not load startup collection '%s'", startup_collection)

    ####################
    ## Private Functions
    ####################

    def _finish_setup(self):
        pass


    ###################
    ## Public Functions
    ###################

    def get_my_window_name(self):
        return self.window_name or "unknown"

    def close_app(self):
        logger.info("close_app called from window '%s'", self.window_name)
        if self.frontend_browser:
            self.frontend_browser.terminate_all()

    def shutdown_system(self):
        """Shutdown the host system (cross-platform) and close frontend windows."""
        logger.info("shutdown_system called from window '%s'", self.window_name)

        # Match managerui/pages/remote.py behavior for platform shutdown commands.
        if sys.platform == 'win32':
            # 1 second delay gives the app a moment to tear down cleanly.
            subprocess.Popen(['shutdown', '/s', '/t', '1'], shell=True)
        elif sys.platform == 'darwin':
            subprocess.Popen(['osascript', '-e', 'tell app "System Events" to shut down'])
        else:
            # Linux: ignore desktop/session inhibitors.
            subprocess.Popen(["systemctl", "poweroff", "-i"])

        if self.frontend_browser:
            self.frontend_browser.terminate_all()

    def get_monitors(self):
        monitors = get_monitors()
        # Return a list of dicts with relevant info
        return [{
            'name': f'Monitor {i}',
            'x': m.x,
            'y': m.y,
            'width': m.width,
            'height': m.height
        } for i, m in enumerate(monitors)]

    def send_event_all_windows(self, message):
        if self.ws_bridge:
            self.ws_bridge.send_event_all(message, exclude=self.window_name)

    def send_event(self, window_name, message):
        if self.ws_bridge:
            self.ws_bridge.send_event(window_name, message)

    def send_event_all_windows_incself(self, message):
        if self.ws_bridge:
            self.ws_bridge.send_event_all_with_iframe(message)

    def get_tables(self, reset=False):
        if reset:
            self.filteredTables = self.allTables

        tables = []
        for table in self.filteredTables:
            # Normalize metaConfig
            meta = {}
            if table.metaConfig:
                if isinstance(table.metaConfig, dict):
                    meta = table.metaConfig
                elif hasattr(table.metaConfig, "getConfig"):
                    meta = table.metaConfig.getConfig()

            # If altvpsid is used for this table, prefer alttitle for frontend display.
            vpinfe_meta = meta.get("VPinFE", {}) if isinstance(meta, dict) else {}
            info_meta = meta.get("Info", {}) if isinstance(meta, dict) else {}
            if isinstance(vpinfe_meta, dict) and isinstance(info_meta, dict):
                alt_vpsid = str(vpinfe_meta.get("altvpsid", "") or "").strip()
                alt_title = str(vpinfe_meta.get("alttitle", "") or "").strip()
                if alt_vpsid and alt_title:
                    info_meta["Title"] = alt_title
                    meta["Info"] = info_meta

            # Ensure detection flags are booleans
            vpx = meta.get("VPXFile", {})
            detect_key_map = {
                "detectnfozzy",
                "detectfleep",
                "detectssf",
                "detectlut",
                "detectscorebit",
                "detectfastflips",
                "detectflex",
            }

            def _to_bool(val):
                if isinstance(val, bool):
                    return val
                if isinstance(val, str):
                    return val.lower() == "true"
                return val == 1

            # Normalize to lowercase-only detection keys.
            for key in detect_key_map:
                vpx[key] = _to_bool(vpx.get(key, False))

            # Addon flags live on the Table object, but mirror them into VPX metadata for theme compatibility.
            vpx["altSoundExists"] = bool(table.altSoundExists)
            vpx["altColorExists"] = bool(table.altColorExists)
            vpx["pupPackExists"] = bool(table.pupPackExists)

            table_data = {
                "tableDirName": table.tableDirName,
                "fullPathTable": table.fullPathTable,
                "fullPathVPXfile": table.fullPathVPXfile,
                "BGImagePath": table.BGImagePath,
                "DMDImagePath": table.DMDImagePath,
                "TableImagePath": table.TableImagePath,
                "FSSImagePath": table.FSSImagePath,
                "WheelImagePath": table.WheelImagePath,
                "CabImagePath": table.CabImagePath,
                "realDMDImagePath": table.realDMDImagePath,
                "realDMDColorImagePath": table.realDMDColorImagePath,
                "FlyerImagePath": table.FlyerImagePath,
                "TableVideoPath": table.TableVideoPath,
                "BGVideoPath": table.BGVideoPath,
                "DMDVideoPath": table.DMDVideoPath,
                "AudioPath": table.AudioPath,
                "pupPackExists": table.pupPackExists,
                "altColorExists": table.altColorExists,
                "altSoundExists": table.altSoundExists,
                "meta": meta
            }
            tables.append(table_data)

        self.jsTableDictData = json.dumps(tables)
        return self.jsTableDictData


    def get_collections(self):
        config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
        c = VPXCollections(config_dir / "collections.ini")
        return c.get_collections_name()

    def set_tables_by_collection(self, collection):
        """Set filtered tables based on collection from collections.ini."""
        self.current_collection = collection
        config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
        c = VPXCollections(config_dir / "collections.ini")

        # Check if this is a filter-based collection
        if c.is_filter_based(collection):
            # Get the filter parameters and apply them
            filters = c.get_filters(collection)
            table_filters = TableListFilters(self.allTables)
            self.filteredTables = table_filters.apply_filters(
                letter=filters['letter'],
                theme=filters['theme'],
                table_type=filters['table_type'],
                manufacturer=filters['manufacturer'],
                year=filters['year'],
                rating=filters.get('rating', 'All'),
                rating_or_higher=filters.get('rating_or_higher', 'false'),
            )
            # Update current filter state to match the collection
            self.current_filters = {
                'letter': filters['letter'],
                'theme': filters['theme'],
                'type': filters['table_type'],
                'manufacturer': filters['manufacturer'],
                'year': filters['year'],
                'rating': filters.get('rating', 'All'),
                'rating_or_higher': str(filters.get('rating_or_higher', 'false')).lower() in ('1', 'true', 'yes', 'on'),
            }
            # Apply the sort order
            self.current_sort = filters['sort_by']
            self.apply_sort(filters['sort_by'])
        else:
            # VPS ID-based collection
            self.filteredTables = c.filter_tables(self.allTables, collection)
            # Reset filter state since we're using VPS IDs
            self.current_filters = {
                'letter': None,
                'theme': None,
                'type': None,
                'manufacturer': None,
                'year': None,
                'rating': None,
                'rating_or_higher': False,
            }

    def save_filter_collection(
        self,
        name,
        letter="All",
        theme="All",
        table_type="All",
        manufacturer="All",
        year="All",
        sort_by="Alpha",
        rating="All",
        rating_or_higher=False,
    ):
        """Save current filter settings as a named collection."""
        config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
        c = VPXCollections(config_dir / "collections.ini")
        rating_or_higher_flag = str(rating_or_higher).strip().lower() in ('1', 'true', 'yes', 'on')
        try:
            c.add_filter_collection(
                name,
                letter,
                theme,
                table_type,
                manufacturer,
                year,
                rating,
                'true' if rating_or_higher_flag else 'false',
                sort_by,
            )
            c.save()
            return {"success": True, "message": f"Filter collection '{name}' saved successfully"}
        except ValueError as e:
            return {"success": False, "message": str(e)}

    def get_current_filter_state(self):
        """Return current filter state for UI synchronization."""
        return self.current_filters

    def get_current_sort_state(self):
        """Return current sort state for UI synchronization."""
        return self.current_sort

    def get_current_collection(self):
        """Return current collection name for UI synchronization."""
        return self.current_collection or 'None'

    def get_filter_letters(self):
        """Get available starting letters from ALL tables."""
        filters = TableListFilters(self.allTables)
        return filters.get_available_letters()

    def get_filter_themes(self):
        """Get available themes from ALL tables."""
        filters = TableListFilters(self.allTables)
        return filters.get_available_themes()

    def get_filter_types(self):
        """Get available table types from ALL tables."""
        filters = TableListFilters(self.allTables)
        return filters.get_available_types()

    def get_filter_manufacturers(self):
        """Get available manufacturers from ALL tables."""
        filters = TableListFilters(self.allTables)
        return filters.get_available_manufacturers()

    def get_filter_years(self):
        """Get available years from ALL tables."""
        filters = TableListFilters(self.allTables)
        return filters.get_available_years()

    def apply_filters(self, letter=None, theme=None, table_type=None, manufacturer=None, year=None, rating=None, rating_or_higher=None):
        """
        Apply VPSdb filters to the full table list.
        These filters work independently of collections.
        Returns the count of filtered tables.
        """
        self.current_collection = None
        # Update filter state
        if letter is not None:
            self.current_filters['letter'] = letter
        if theme is not None:
            self.current_filters['theme'] = theme
        if table_type is not None:
            self.current_filters['type'] = table_type
        if manufacturer is not None:
            self.current_filters['manufacturer'] = manufacturer
        if year is not None:
            self.current_filters['year'] = year
        if rating is not None:
            self.current_filters['rating'] = rating
        if rating_or_higher is not None:
            self.current_filters['rating_or_higher'] = str(rating_or_higher).strip().lower() in ('1', 'true', 'yes', 'on')

        logger.debug(
            "Applying filters: letter=%s, theme=%s, type=%s, manufacturer=%s, year=%s, rating=%s, rating_or_higher=%s",
            self.current_filters['letter'],
            self.current_filters['theme'],
            self.current_filters['type'],
            self.current_filters['manufacturer'],
            self.current_filters['year'],
            self.current_filters['rating'],
            self.current_filters['rating_or_higher'],
        )

        # Always start from the full table list
        filters = TableListFilters(self.allTables)
        self.filteredTables = filters.apply_filters(
            letter=self.current_filters['letter'],
            theme=self.current_filters['theme'],
            table_type=self.current_filters['type'],
            manufacturer=self.current_filters['manufacturer'],
            year=self.current_filters['year'],
            rating=self.current_filters['rating'],
            rating_or_higher=self.current_filters['rating_or_higher'],
        )

        count = len(self.filteredTables)
        logger.debug("Filtered tables count: %s", count)
        return count

    def reset_filters(self):
        """Reset all VPSdb filters back to full table list."""
        self.filteredTables = self.allTables
        self.current_filters = {
            'letter': None,
            'theme': None,
            'manufacturer': None,
            'type': None,
            'year': None,
            'rating': None,
            'rating_or_higher': False,
        }

    def apply_sort(self, sort_type):
        """
        Sort the current filtered tables.
        sort_type: 'Alpha', 'Newest', 'LastRun', or 'Highest StartCount'
        Returns the count of sorted tables.
        """
        self.current_sort = sort_type
        logger.debug("Applying sort: %s", sort_type)

        if sort_type == 'Alpha':
            # Sort alphabetically by VPSdb.name
            self.filteredTables.sort(
                key=lambda t: (
                    (t.metaConfig or {})
                    .get("VPSdb", {})
                    .get("name", "")
                    .lower()
                )
            )
        elif sort_type == 'Newest':
            # Sort by creation_time (newest first)
            self.filteredTables.sort(
                key=lambda t: t.creation_time if t.creation_time is not None else 0,
                reverse=True
            )
        elif sort_type == 'LastRun':
            # Sort by User.LastRun (most recent first), then title for deterministic ties.
            def _sort_key(t):
                meta = t.metaConfig if isinstance(t.metaConfig, dict) else {}
                user = meta.get("User", {}) if isinstance(meta.get("User"), dict) else {}
                try:
                    last_run = int(user.get("LastRun", -1)) if isinstance(user, dict) else -1
                except (TypeError, ValueError):
                    last_run = -1
                title = str((meta.get("Info", {}) if isinstance(meta, dict) else {}).get("Title", "")).lower()
                return (-last_run, title)

            self.filteredTables.sort(key=_sort_key)
        elif sort_type == 'Highest StartCount':
            # Sort by User.StartCount (highest first), then title for deterministic ties.
            def _sort_key(t):
                meta = t.metaConfig if isinstance(t.metaConfig, dict) else {}
                user = meta.get("User", {}) if isinstance(meta, dict) else {}
                try:
                    start_count = int(user.get("StartCount", 0)) if isinstance(user, dict) else 0
                except (TypeError, ValueError):
                    start_count = 0
                title = str((meta.get("Info", {}) if isinstance(meta, dict) else {}).get("Title", "")).lower()
                return (-start_count, title)

            self.filteredTables.sort(key=_sort_key)

        count = len(self.filteredTables)
        logger.debug("Sorted %s tables by %s", count, sort_type)
        return count

    def console_out(self, output):
        logger.info("Win: %s - %s", self.window_name, output)
        return output

    def get_joymaping(self):
        return {
            'joyleft': self._iniConfig.config['Input'].get('joyleft', '0'),
            'joyright': self._iniConfig.config['Input'].get('joyright', '0'),
            'joyup': self._iniConfig.config['Input'].get('joyup', '0'),
            'joydown': self._iniConfig.config['Input'].get('joydown', '0'),
            'joyselect': self._iniConfig.config['Input'].get('joyselect', '0'),
            'joymenu': self._iniConfig.config['Input'].get('joymenu', '0'),
            'joyback': self._iniConfig.config['Input'].get('joyback', '0'),
            'joyexit': self._iniConfig.config['Input'].get('joyexit', '0'),
            'joycollectionmenu': self._iniConfig.config['Input'].get('joycollectionmenu', '0')
        }

    def set_button_mapping(self, button_name, button_index):
        """Set a gamepad button mapping and save to config."""
        valid_buttons = [
            'joyleft', 'joyright', 'joyup', 'joydown',
            'joyselect', 'joymenu', 'joyback', 'joyexit', 'joycollectionmenu'
        ]

        if button_name not in valid_buttons:
            return {"success": False, "message": f"Invalid button name: {button_name}"}

        try:
            # Set the value in the config
            self._iniConfig.config.set('Input', button_name, str(button_index))
            # Save to file
            self._iniConfig.save()
            return {"success": True, "message": f"Mapped {button_name} to button {button_index}"}
        except Exception as e:
            return {"success": False, "message": f"Error saving mapping: {str(e)}"}

    def launch_table(self, index):
        table = self.filteredTables[index]
        vpx = table.fullPathVPXfile
        vpxbin = self._iniConfig.config['Settings'].get('vpxbinpath', '')
        vpxbin_path, source_key, _ = get_effective_launcher(vpxbin, table.metaConfig)
        if not vpxbin_path:
            logger.warning("No launcher configured (checked VPinFE.%s and Settings.vpxbinpath)", source_key)
            return
        if not vpxbin_path.exists():
            logger.warning("Launcher not found (%s): %s", source_key, vpxbin_path)
            return
        # Track the table play
        self._track_table_play(table)

        stop_dof_service()
        launch_started_at = None
        try:
            global_ini_override = self._iniConfig.config['Settings'].get('globalinioverride', '').strip()
            tableini_override = resolve_launch_tableini_override(
                vpx,
                self._iniConfig.config['Settings'].get('globaltableinioverrideenabled', 'false'),
                self._iniConfig.config['Settings'].get('globaltableinioverridemask', ''),
            )
            cmd = build_vpx_launch_command(
                launcher_path=str(vpxbin_path),
                vpx_table_path=vpx,
                global_ini_override=global_ini_override,
                tableini_override=tableini_override,
            )
            logger.info("Launching: %s", cmd)
            launch_env = os.environ.copy()
            launch_env.update(
                parse_launch_env_overrides(
                    self._iniConfig.config['Settings'].get('vpxlaunchenv', '')
                )
            )

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                env=launch_env)
            launch_started_at = time.time()
            self._increment_user_start_count(table)

            startup_detected = False
            for line in process.stdout:
                if not startup_detected and "Startup done" in line:
                    startup_detected = True
                    self.send_event_all_windows_incself({"type": "TableRunning"})
                    logger.info("table running")

            process.wait()
        finally:
            start_dof_service_if_enabled(self._iniConfig)

        if launch_started_at is not None:
            elapsed_seconds = max(0.0, time.time() - launch_started_at)
            self._add_user_runtime_minutes(table, elapsed_seconds)
            self._update_user_score_from_nvram(table)

        # macOS: re-activate Chromium windows so they return to foreground
        # after VPX exits (kiosk windows don't auto-regain focus on macOS)
        if sys.platform == "darwin" and self.frontend_browser:
            self.frontend_browser.activate_all_mac()

        # Delete NVRAM file if configured for this table
        self._delete_nvram_if_configured(table)

        self.send_event_all_windows_incself({"type": "TableLaunchComplete"})

    def get_table_rating(self, index):
        """Get User.Rating for a table index in the current filtered list."""
        try:
            table = self.filteredTables[index]
        except Exception:
            return 0

        config = table.metaConfig or {}
        if not isinstance(config, dict):
            return 0

        user = config.get("User", {})
        raw = user.get("Rating", 0) if isinstance(user, dict) else 0
        try:
            rating = int(raw)
        except (TypeError, ValueError):
            rating = 0
        return max(0, min(5, rating))

    def set_table_rating(self, index, rating):
        """Set User.Rating (0-5) for a table index in the current filtered list."""
        table = self.filteredTables[index]
        config = table.metaConfig or {}
        if not isinstance(config, dict):
            config = {}

        user = self._get_or_create_user_meta(config)
        try:
            normalized = int(rating)
        except (TypeError, ValueError):
            normalized = 0
        normalized = max(0, min(5, normalized))

        user["Rating"] = normalized
        self._persist_table_meta(table, config)
        logger.info("Updated User.Rating for %s -> %s", table.tableDirName, normalized)
        return {"success": True, "rating": normalized}

    def _track_table_play(self, table):
        """Track a table play by adding it to the Last Played collection."""

        meta = table.metaConfig or {}
        info = meta.get("Info", {})
        vpsid = info.get("VPSId")

        if not vpsid:
            logger.debug("Table has no VPSId, cannot track play")
            return

        config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
        c = VPXCollections(config_dir / "collections.ini")

        # Create Last Played collection if it doesn't exist
        if "Last Played" not in c.get_collections_name():
            logger.info("Creating 'Last Played' collection")
            c.add_collection("Last Played", vpsids=[])

        last_played_ids = c.get_vpsids("Last Played")

        if vpsid in last_played_ids:
            last_played_ids.remove(vpsid)

        last_played_ids.insert(0, vpsid)
        last_played_ids = last_played_ids[:30]

        c.config["Last Played"]["vpsids"] = ",".join(last_played_ids)
        c.save()

        logger.info("Tracked table play: %s (now %s in Last Played)", vpsid, len(last_played_ids))

    def _get_meta_file_path(self, table):
        return Path(table.fullPathTable) / f"{table.tableDirName}.info"

    def _persist_table_meta(self, table, config):
        meta_file_path = self._get_meta_file_path(table)
        meta_file = MetaConfig(str(meta_file_path))
        meta_file.data = config
        meta_file.writeConfig()
        table.metaConfig = config

    def _get_or_create_user_meta(self, config):
        user = config.setdefault("User", {})
        user.setdefault("Rating", 0)
        user.setdefault("Favorite", 0)
        user.setdefault("LastRun", None)
        user.setdefault("StartCount", 0)
        user.setdefault("RunTime", 0)
        user.setdefault("Tags", [])
        return user

    def _update_user_score_from_nvram(self, table):
        config = table.metaConfig or {}
        if not isinstance(config, dict):
            logger.warning("Could not update Score: invalid table metadata for %s", table.tableDirName)
            return

        rom = str(config.get("Info", {}).get("Rom", "") or "").strip()
        if not rom:
            logger.debug("No ROM name found for %s, skipping score update", table.tableDirName)
            return

        primary_score_path = Path(table.fullPathTable) / "pinmame" / "nvram" / f"{rom}.nv"
        fallback_score_path = Path(table.fullPathTable) / "user" / "VPReg.ini"

        score_path = primary_score_path
        if not score_path.exists():
            if fallback_score_path.exists():
                score_path = fallback_score_path
                logger.debug(
                    "NVRAM file not found for %s, falling back to %s",
                    table.tableDirName,
                    score_path,
                )
            else:
                logger.debug(
                    "No score source found for %s. Checked %s and %s",
                    table.tableDirName,
                    primary_score_path,
                    fallback_score_path,
                )
                return

        try:
            parsed_result = read_rom(rom, str(score_path))
            score_data = result_to_jsonable(rom, parsed_result, str(score_path))
        except KeyError:
            logger.debug("ROM %s is not supported for score parsing", rom)
            return

        except Exception:
            logger.exception("Failed to parse score data for %s from %s", table.tableDirName, score_path)
            return

        if not score_data:
            logger.debug("Parsed score data for %s was empty, skipping metadata update", table.tableDirName)
            return

        user = self._get_or_create_user_meta(config)
        user["Score"] = score_data
        self._persist_table_meta(table, config)
        logger.info("Updated User.Score for %s from %s", table.tableDirName, score_path)

    def _increment_user_start_count(self, table):
        config = table.metaConfig or {}
        if not isinstance(config, dict):
            logger.warning("Could not increment StartCount: invalid table metadata for %s", table.tableDirName)
            return

        user = self._get_or_create_user_meta(config)
        try:
            user["StartCount"] = int(user.get("StartCount", 0)) + 1
        except (TypeError, ValueError):
            user["StartCount"] = 1
        user["LastRun"] = int(time.time())
        self._persist_table_meta(table, config)
        logger.info("Updated User.StartCount for %s -> %s", table.tableDirName, user["StartCount"])

    def _add_user_runtime_minutes(self, table, elapsed_seconds):
        config = table.metaConfig or {}
        if not isinstance(config, dict):
            logger.warning("Could not update RunTime: invalid table metadata for %s", table.tableDirName)
            return

        # Round up partial minutes so short plays are still counted.
        session_minutes = int((elapsed_seconds + 59) // 60)
        user = self._get_or_create_user_meta(config)
        try:
            prior_runtime = int(user.get("RunTime", 0))
        except (TypeError, ValueError):
            prior_runtime = 0
        user["RunTime"] = prior_runtime + session_minutes
        self._persist_table_meta(table, config)
        logger.info(
            "Updated User.RunTime for %s: +%s min (total=%s)",
            table.tableDirName,
            session_minutes,
            user["RunTime"],
        )

    def _delete_nvram_if_configured(self, table):
        """Delete the NVRAM .nv file if deletedNVRamOnClose is enabled for this table."""
        meta = table.metaConfig or {}
        if isinstance(meta, dict):
            config = meta
        elif hasattr(meta, "getConfig"):
            config = meta.getConfig()
        else:
            return

        vpinfe = config.get("VPinFE", {})
        if not vpinfe.get("deletedNVRamOnClose", False):
            return

        rom = config.get("Info", {}).get("Rom", "")
        if not rom:
            logger.warning("No ROM name found for table, skipping NVRAM deletion")
            return

        nvram_path = Path(table.fullPathTable) / "pinmame" / "nvram" / f"{rom}.nv"
        if nvram_path.exists():
            nvram_path.unlink()
            logger.info("Deleted NVRAM file: %s", nvram_path)
        else:
            logger.info("NVRAM file not found (nothing to delete): %s", nvram_path)

    def build_metadata(self, download_media=True, update_all=False):
        """
        Trigger buildMetaData from the frontend.
        This runs in a background thread and returns progress/log updates via window events.

        Args:
            download_media: Whether to download media files
            update_all: Whether to update all tables (even if meta.ini exists)

        Returns:
            dict with success status and message
        """
        from clioptions import buildMetaData
        import threading
        from queue import Queue

        # Use a queue to safely pass events from background thread
        event_queue = Queue()

        def progress_callback(current, total, message):
            """Queue progress updates."""
            logger.debug("[buildmeta] Progress: %s/%s - %s", current, total, message)
            event_queue.put({
                'type': 'buildmeta_progress',
                'current': current,
                'total': total,
                'message': message
            })

        def log_callback(message):
            """Queue log messages."""
            logger.info("[buildmeta] %s", message)
            event_queue.put({
                'type': 'buildmeta_log',
                'message': message
            })

        def run_build():
            """Run buildMetaData in background thread."""
            try:
                result = buildMetaData(
                    downloadMedia=download_media,
                    updateAll=update_all,
                    progress_cb=progress_callback,
                    log_cb=log_callback
                )
                # Queue completion event
                event_queue.put({
                    'type': 'buildmeta_complete',
                    'result': result
                })
                # Refresh table list after completion
                self.allTables = TableParser(self._iniConfig.config['Settings']['tablerootdir'], self._iniConfig).getAllTables()
                self.filteredTables = self.allTables
            except Exception as e:
                # Queue error event
                event_queue.put({
                    'type': 'buildmeta_error',
                    'error': str(e)
                })
                logger.exception("buildMetaData failed")
            finally:
                # Signal completion
                event_queue.put({'type': 'buildmeta_done'})

        def process_events():
            """Process queued events and send to windows."""
            try:
                logger.debug("[buildmeta] Event processor started")
                while True:
                    # Block until we get an event
                    event = event_queue.get(timeout=30)
                    logger.debug("[buildmeta] Processing event: %s", event['type'])
                    if event['type'] == 'buildmeta_done':
                        logger.debug("[buildmeta] Build complete, stopping event processor")
                        break
                    # Send event to all windows
                    try:
                        self.send_event_all_windows_incself(event)
                        logger.debug("[buildmeta] Sent event to windows: %s", event['type'])
                    except Exception:
                        logger.exception("Error sending event to windows")
            except Exception:
                logger.exception("Error processing buildmeta events")

        # Start build in background thread
        build_thread = threading.Thread(target=run_build, daemon=True)
        build_thread.start()

        # Start event processor in another background thread
        event_thread = threading.Thread(target=process_events, daemon=True)
        event_thread.start()

        return {'success': True, 'message': 'Build metadata started'}

    def _resolve_theme_dir(self, theme_name):
        """Returns the filesystem path to the theme directory."""
        config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
        theme_dir = config_dir / "themes" / theme_name
        if theme_dir.is_dir():
            return theme_dir
        return None

    def get_theme_config(self):
        theme_name = self.get_theme_name()
        theme_dir = self._resolve_theme_dir(theme_name)
        if not theme_dir:
            return None

        theme_path = theme_dir / "config.json"
        logger.debug("theme config path: %s", theme_path)
        try:
            with open(theme_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        except Exception:
            return None

    ###################
    ### For splash page
    ###################

    def get_splashscreen_enabled(self):
        return self._iniConfig.config['Settings'].get('splashscreen', 'true')

    def get_audio_muted(self):
        raw = str(self._iniConfig.config['Settings'].get('muteaudio', 'false')).strip().lower()
        return raw in ('1', 'true', 'yes', 'on')

    def set_audio_muted(self, muted):
        if isinstance(muted, bool):
            muted_flag = muted
        else:
            muted_flag = str(muted or '').strip().lower() in ('1', 'true', 'yes', 'on')
        self._iniConfig.config.set('Settings', 'muteaudio', 'true' if muted_flag else 'false')
        self._iniConfig.save()
        self.send_event_all_windows_incself({
            'type': 'AudioMuteChanged',
            'muted': muted_flag,
        })
        return muted_flag

    def get_theme_name(self):
        theme_name = str(self._iniConfig.config['Settings'].get('theme', 'Revolution')).strip()
        return theme_name or 'Revolution'

    def get_table_orientation(self):
        return self._iniConfig.config['Displays'].get('tableorientation', 'landscape')

    def get_table_rotation(self):
        raw = str(self._iniConfig.config['Displays'].get('tablerotation', '0')).strip()
        if raw == '':
            return 0
        try:
            return int(float(raw))
        except (ValueError, TypeError):
            return 0

    def get_cab_mode(self):
        raw = str(self._iniConfig.config['Displays'].get(
            'cabmode',
            self._iniConfig.config['Settings'].get('cabmode', 'false')
        )).strip().lower()
        return raw in ('1', 'true', 'yes', 'on')
    def get_theme_assets_port(self):
        return int(self._iniConfig.config['Network'].get('themeassetsport', '8000'))

    def get_theme_index_page(self):
        theme_name = self.get_theme_name()
        port = self.get_theme_assets_port()
        window_name = self.get_my_window_name()
        url = f'http://127.0.0.1:{port}/themes/{theme_name}/index_{window_name}.html?window={window_name}'
        return url
