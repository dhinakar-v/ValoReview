# Archive

Point-in-time documents. They were true when written and are kept for the
reasoning in them, not as a description of the tree.

**Handoffs** (`*-handoff.md`) are session summaries: what a session did, what it
tried that did not work, and what it left for the next one. Seven of them span
21–22 August 2026, from the first container reader to the browser viewer. Every
one describes a working tree that no longer exists — `CLAUDE.md` is the durable
record.

**`webapp-01-merge-the-fast-decoder.md`** and **`webapp-02-serve-the-fast-decode.md`**
are implementation plans for work that shipped. `webapp-03-map-viewers.md` is
still in `docs/` because it is not finished.

**`valorant-replay-prompt.md`** is the original project brief. It specifies a
CustomTkinter desktop application, which is what this project was and is not any
more. Two of its requirements were found to be unbuildable from a `.vrf` and are
recorded as such in `CLAUDE.md`: the WIN/LOSS badge (no local player) and any
per-player health, armour or economy (not replicated to a spectator recording).

**`valorant-api.md`** is the endpoint and DTO reference for Riot's authenticated
API. Nothing in the project calls it any more — `valapi.py` and `valcatalog.py`
were removed once it was established that the server never passed a catalogue to
anything — but Riot's endpoints stay true whether or not this repository uses
them, and `val-match-v1` is still where player names, ranks and per-round economy
would come from if a production key were ever granted.
