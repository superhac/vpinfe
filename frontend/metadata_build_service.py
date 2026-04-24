from __future__ import annotations

import logging
import threading
from queue import Queue


logger = logging.getLogger("vpinfe.frontend.metadata_build_service")


def start_build(api, *, build_metadata_func, ensure_tables_loaded_func, download_media=True, update_all=False):
    event_queue = Queue()

    def progress_callback(current, total, message):
        logger.debug("[buildmeta] Progress: %s/%s - %s", current, total, message)
        event_queue.put({
            "type": "buildmeta_progress",
            "current": current,
            "total": total,
            "message": message,
        })

    def log_callback(message):
        logger.info("[buildmeta] %s", message)
        event_queue.put({
            "type": "buildmeta_log",
            "message": message,
        })

    def run_build():
        try:
            result = build_metadata_func(
                downloadMedia=download_media,
                updateAll=update_all,
                progress_cb=progress_callback,
                log_cb=log_callback,
            )
            event_queue.put({"type": "buildmeta_complete", "result": result})
            api.allTables = ensure_tables_loaded_func(reload=True)
            api.filteredTables = api.allTables
        except Exception as exc:
            event_queue.put({"type": "buildmeta_error", "error": str(exc)})
            logger.exception("buildMetaData failed")
        finally:
            event_queue.put({"type": "buildmeta_done"})

    def process_events():
        try:
            logger.debug("[buildmeta] Event processor started")
            while True:
                event = event_queue.get(timeout=30)
                logger.debug("[buildmeta] Processing event: %s", event["type"])
                if event["type"] == "buildmeta_done":
                    break
                try:
                    api.send_event_all_windows_incself(event)
                except Exception:
                    logger.exception("Error sending event to windows")
        except Exception:
            logger.exception("Error processing buildmeta events")

    threading.Thread(target=run_build, daemon=True).start()
    threading.Thread(target=process_events, daemon=True).start()
    return {"success": True, "message": "Build metadata started"}
