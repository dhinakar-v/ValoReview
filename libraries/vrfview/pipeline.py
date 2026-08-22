"""
The four steps that turn a path into a replay anything can draw.

Extracted from the app window so it is not the toolkit's property.  The order
is the whole content of the module and it is load-bearing, which is the reason
it lives somewhere importable rather than being retyped by each caller: an
interface that gets it wrong does not crash, it just shows ten players called
`Hunter` and a team split cross-checked against nothing.

`attach_stored` cannot decode.  It picks up a sidecar or a cache entry and
nothing else, so it costs milliseconds when there is something and nothing when
there is not -- which is what makes it safe to have on the open path at all.
A caller that wants the four-minute decode asks `tracks.attach` for it directly
and afterwards runs `names.resolve` again, because the codenames only exist
once the stream has been read.

This module reaches `tracks`, and `tracks` reaches the decoder and `vrf_reader`.
It is therefore not a model-layer module in the sense `vrfview.model` and its
neighbours are, and it is deliberately kept out of that set: the rule those
modules keep is that they run with no display *and no decoder*, and this one
opens files.  It imports no toolkit, which is the property a server or a CLI
actually needs from it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vrfview import infer, loader, names, tracks

if TYPE_CHECKING:
    from pathlib import Path

    from vrfview.model import Replay


def open_replay(path: str | Path) -> Replay:
    """
    Read, infer, attach anything already decoded, then name.

    `infer` cross-checks its team split against the codenames and `names` needs
    them to name anybody, so naming has to happen after a stored decode has
    arrived or every agent stays a `Hunter`.
    """
    replay = infer.annotate(loader.load(path))
    tracks.attach_stored(replay, path)
    return names.resolve(replay)
