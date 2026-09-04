"""Binds the lifecycle vocabulary to the things that actually start and stop.

Every stop and restart of this process ends the same way: `run_frontend_loop` returns and
`main.py` runs `shutdown_services`. Reaching for the browser directly is what used to skip
it, so those performers only ever make that loop return.

Stopping a table is the exception and does not touch the loop: the table is a child of
this install rather than a part of it, and closing one leaves VPinFE and its windows up.
"""

from __future__ import annotations

import logging

from common import events, lifecycle
from common.config_access import cfg_bool
from common.host import launch_state, system_actions

logger = logging.getLogger("vpinfe.frontend.lifecycle")

_config_store = None
_bridge = None


def confirm_scopes():
    """What asks first: quitting VPinFE and powering off the machine, or nothing.

    Stopping the frontend is not in it. The windows reopen from the Manager UI, so there
    is nothing to lose and it is the scope you would meet most often - a prompt there is
    the one that trains you to dismiss prompts.
    """
    if _config_store is None or not cfg_bool(_config_store, "frontend", "confirm"):
        return ()
    return (lifecycle.APP, lifecycle.SYSTEM)


def wants_confirmation(scope: str) -> bool:
    """Whether a surface should put the question to the user before asking us. The
    bridge to a window is one-way, so the browser asks and reports the answer."""
    return scope in confirm_scopes()


def _announce(request: lifecycle.Request) -> None:
    events.emit(
        events.LIFECYCLE_ACTING,
        scope=request.scope,
        action=request.action,
        surface=request.origin.surface,
        address=request.origin.address,
        reason=request.reason,
        description=request.describe(),
    )


def _notice(*, scope, action, surface, address, description, **_payload) -> None:
    """Tell the windows what is happening, unless they are the ones who asked.

    The rule is a notice on every listening surface that did not start it. The window
    that did already has the answer on screen, so telling it again would talk over its
    own confirmation.
    """
    if _bridge is None:
        return
    message = {"type": "LifecycleActing", "scope": scope, "action": action,
               "description": description, "origin": surface}
    if surface == lifecycle.SURFACE_FRONTEND and address:
        _bridge.send_event_all(message, exclude=address)
    else:
        _bridge.send_event_all(message)


def install(*, config_store, config_dir, frontend_browser, shutdown_event,
            ws_bridge=None, open_windows=None) -> None:
    """Wire this process's performers. Called once, from startup."""
    global _config_store, _bridge
    _config_store = config_store
    _bridge = ws_bridge
    # Unsubscribe first: install is called once at startup, but subscribing twice would
    # send every window two copies of the same notice.
    events.unsubscribe(events.LIFECYCLE_ACTING, _notice)
    if ws_bridge is not None:
        events.subscribe(events.LIFECYCLE_ACTING, _notice)

    def stop_app(_request):
        # Both, because which one ends the wait depends on whether windows are open:
        # headless blocks on the event, windowed blocks on the browser.
        shutdown_event.set()
        frontend_browser.terminate_all()

    def restart_app(_request):
        # main.py checks for this after the services are down, so the sentinel has to be
        # written before anything unblocks the loop.
        system_actions.request_app_restart(config_dir)
        stop_app(_request)

    def stop_frontend(_request):
        frontend_browser.terminate_all()

    def restart_frontend(_request):
        frontend_browser.terminate_all()
        if open_windows is not None:
            open_windows()

    def stop_system(request):
        system_actions.shutdown_system()
        stop_app(request)

    def restart_system(request):
        system_actions.reboot_system()
        stop_app(request)

    def stop_table(_request):
        launch_state.stop()

    lifecycle.register_performer(lifecycle.APP, lifecycle.STOP, stop_app)
    lifecycle.register_performer(lifecycle.APP, lifecycle.RESTART, restart_app)
    lifecycle.register_performer(lifecycle.FRONTEND, lifecycle.STOP, stop_frontend)
    lifecycle.register_performer(lifecycle.SYSTEM, lifecycle.STOP, stop_system)
    lifecycle.register_performer(lifecycle.SYSTEM, lifecycle.RESTART, restart_system)
    lifecycle.register_performer(lifecycle.TABLE, lifecycle.STOP, stop_table)

    # Only registered when the caller knows how to open windows. An instance that cannot
    # reports "nothing performs this" rather than silently going dark.
    if open_windows is not None:
        lifecycle.register_performer(lifecycle.FRONTEND, lifecycle.START,
                                     lambda _request: open_windows())
        lifecycle.register_performer(lifecycle.FRONTEND, lifecycle.RESTART,
                                     restart_frontend)

    lifecycle.register_notifier(_announce)


def request(scope: str, action: str, *, origin: lifecycle.Origin, reason: str = "",
            already_confirmed: bool = False) -> bool:
    """Make a request under this process's configured confirm policy.

    `already_confirmed` satisfies the policy rather than bypassing it: a surface that
    does not ask still gets asked.
    """
    scopes = () if already_confirmed else confirm_scopes()
    return lifecycle.request(scope, action, origin=origin,
                             confirm_scopes=scopes, reason=reason)
