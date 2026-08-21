# Third-party notices

This project has no runtime dependencies, but it does contain code ported by
hand from other projects. Their licences are reproduced here in full, as those
licences require.

Each ported module names its upstream source file in its own docstring; this
file is the licence record, not the index.

---

## ValorantReplayParser

<https://github.com/michel-giehl/ValorantReplayParser>

`libraries/vrfnet/payload_transform.py` is a Python port of that project's
payload de-obfuscation, and `tests/test_payload_transform.py` reuses its
known-answer test vectors verbatim. Both derive from:

- `src/Replay.Encoding/PayloadEncryption/ValorantSeededTransformHelpers.cs`
- `src/Replay.Encoding/PayloadEncryption/VersionedTransforms/ValorantSeededTransform*.cs`
- `tests/Replay.Encoding.Tests/PayloadEncryption/ValorantSeededTransformTests.cs`

```
MIT License

Copyright (c) 2026 Michel Giehl

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Not yet ported, but the likely next sources from the same project and the same
licence: `Replay.Unreal/Parsing/FieldPayloadParser.cs`,
`Replay.Unreal/Parsing/ArchiveVectorReaders.cs`, and
`Replay.Valorant/Movement/ComponentDataStream.cs`.

Its predecessor, `michel-giehl/ValorantReplayParserPlayground` (also MIT), is a
fork of `Shiqan/FortniteReplayDecompressor`. Nothing here is taken from either;
if anything ever is, Shiqan's notice belongs in this file too.

`OozSharp` is **not** used: this project resolves a native Oodle DLL instead
(`libraries/oodlefind.py`).

---

## Disclaimer

This project is an independent tool and is not affiliated with, endorsed by,
sponsored by, or approved by Riot Games. VALORANT, Riot Games, and all related
trademarks are the property of Riot Games, Inc.

It reads replay files the user already has on their own machine. It does not
touch the game client, the game process, or any anti-cheat component.
