"""Converting a library from another frontend into game folders.

It only ever creates. A foreign layout is read and turned into entries of ours; nothing
of the source is written to, and nothing already in the library is changed. That is what
makes it the right first extension: a failed import leaves both libraries exactly as
they were.

Built as an extension deliberately, with no privileged access - the same manifest, the
same scopes and the same context an outside author is given. Where it cannot do
something through them, the contract is short and that is worth finding out.
"""

from __future__ import annotations

from . import api


def register(ctx) -> None:
    api.build(ctx)
    ctx.logger.info("%s source formats readable", len(api.READERS))
