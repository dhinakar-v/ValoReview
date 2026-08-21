# Third-party notices

This project depends on two packages at runtime -- `customtkinter` and
`Pillow`, both installed from PyPI under their own licences -- and it contains
code **ported by hand** from another project. A port is not a dependency: the
code is in this repository, so its licence travels with it, and that licence is
reproduced here in full as it requires.

Each ported module names its upstream source file in its own docstring; this
file is the licence record, not the index.

---

## ValorantReplayParser

<https://github.com/michel-giehl/ValorantReplayParser>

Two modules are Python ports of that project, and each names its own upstream
files in its docstring:

`libraries/vrfnet/payload_transform.py` -- the payload de-obfuscation.
`tests/test_payload_transform.py` reuses its known-answer vectors verbatim.

- `src/Replay.Encoding/PayloadEncryption/ValorantSeededTransformHelpers.cs`
- `src/Replay.Encoding/PayloadEncryption/VersionedTransforms/ValorantSeededTransform*.cs`
- `tests/Replay.Encoding.Tests/PayloadEncryption/ValorantSeededTransformTests.cs`

`libraries/vrfnet/movement.py` -- the movement RPC and the bitstream inside it,
which is where every position in this project comes from.

- `src/Replay.Valorant/Movement/RemoteCharacterUpdatesRpcDecoder.cs`
- `src/Replay.Valorant/Movement/ComponentDataStream.cs`

`libraries/vrfnet/properties.py` is **not** a port: the property loop it runs
is the documented UE one, reached once the transform above is undone.

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

Not ported, and the likely next sources from the same project and the same
licence should more of the payload be decoded: `Replay.Unreal/Parsing/
FieldPayloadParser.cs` and `Replay.Unreal/Parsing/ArchiveVectorReaders.cs`.

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

Map images, agent portraits and callout names come from valorant-api.com, a
community mirror of Riot's published content catalogue; they are Riot's assets,
cached locally under `assets/` and never redistributed by this repository,
which gitignores that directory. The transport glyphs in `assets/icons/` are
drawn by `scripts/make_icons.py` and belong to this project.
