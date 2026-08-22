"""
Which builds can be decoded, and how their payloads are unwhitened.

This was a full port of the Unreal net stack -- demo frames, bunches, actor
channels, the package map, the property loop and the movement RPC -- and it
decoded the reference capture correctly.  It was replaced by
`csharp/VrfPositions`, which does the identical decode in about four seconds
where this took about four minutes, and then kept for a while as an independent
check on it.  It has been cut back to the two modules the project still uses.

What is left is a **table**, not a decoder:

  * `payload_transform` names every build branch a decode is possible for, and
    carries the keystream each one whitens its content-block payloads with.
    `vrfview.tracks` calls `transform_for` purely as a gate -- an unsupported
    build must raise before anything is decompressed -- and `vrfhome.scan` tests
    membership of `SUPPORTED_BRANCHES` so a capture that can never produce a map
    is not offered as playable.  **Never add a nearest-version fallback**: an
    unsupported build has to raise by name, or a porting bug becomes
    indistinguishable from a version mismatch.
  * `bitreader` is the LSB-first reader the transform's own test uses to prove
    its output is stock UE framing rather than merely different bytes.

The branch list is a mirror of what the C# decoder supports, not its source.
Adding a build means adding it in both places.
"""
