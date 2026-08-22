"""
The match list: what a library of `.vrf` files says about itself.

`scan` opens no socket and reads only plain chunks, so a whole library is
described without an Oodle DLL and without decompressing anything.  `prewarm`
fills the position cache from that list on a background worker.  Both are read
by `vrfserve`, which is the only thing that renders them.
"""
