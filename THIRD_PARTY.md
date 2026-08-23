# Third-party notices

This project depends on packages at runtime -- `customtkinter`, `Pillow`,
`fastapi`, `uvicorn` on the Python side and a short list in `web/package.json`
on the browser side, all installed from their registries under their own
licences -- and it contains code **ported by hand** from another project. A
port is not a dependency: the code is in this repository, so its licence
travels with it, and that licence is reproduced here in full as it requires.

The same is true of the typefaces. `web/src/fonts/` holds four `woff2` files
that are **in this repository**, not fetched at run time, so their licence
travels with them and is recorded below.

Since the positions decoder moved to `csharp/VrfPositions`, there is also a
third relationship, and it is neither of those: this repository contains a
small C# program that **compiles against** ValorantReplayParser's libraries.
Nothing of theirs is copied in, but the resulting binary links their code and
the code beneath it, so the section on OozSharp below matters before that
binary is given to anybody.

Each ported module names its upstream source file in its own docstring; this
file is the licence record, not the index.

---

## ValorantReplayParser

<https://github.com/michel-giehl/ValorantReplayParser>

This project reaches that work in two ways.

**Referenced, not vendored.** `csharp/VrfPositions` is a small C# program that
references the upstream project as a library and is where every position in
this project now comes from. Nothing of it is copied here; `runners\
build-decoder.bat` builds against a clone. **Do not take its decompressor** --
`OozSharpOodleDecompressor` wraps OozSharp, which carries a GPLv3 header under
an MIT package.

**Ported.** `libraries/vrfnet/payload_transform.py` is a Python port of the
payload de-obfuscation, and `tests/test_payload_transform.py` reuses its
known-answer vectors verbatim.

- `src/Replay.Encoding/PayloadEncryption/ValorantSeededTransformHelpers.cs`
- `src/Replay.Encoding/PayloadEncryption/VersionedTransforms/ValorantSeededTransform*.cs`
- `tests/Replay.Encoding.Tests/PayloadEncryption/ValorantSeededTransformTests.cs`

A port of the movement RPC and of the surrounding net stack lived here too,
in `libraries/vrfnet/`. It was replaced by the C# decoder above and has been
removed; nothing of it remains beyond the transform and its bit reader.

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

---

## OozSharp, and a licence to be careful about

The Python pipeline still resolves a native Oodle DLL (`libraries/oodlefind.py`)
and uses **no** OozSharp. But `csharp/VrfPositions` references
`Replay.Valorant`, which references `Replay.Encoding`, which takes a NuGet
dependency on **`OozSharp 3.0.1`** -- so a built `vrf-positions.exe` contains
it. That is why this section exists.

OozSharp is not a standalone project. It lives at `src/OozSharp/` inside
[`Shiqan/FortniteReplayDecompressor`](https://github.com/Shiqan/FortniteReplayDecompressor),
whose repository `LICENSE` -- the one the NuGet package ships -- is MIT,
`Copyright (c) 2020-2026 Shiqan`. **However**, its `Kraken.cs` carries this
header:

```
=== Kraken Decompressor for Windows ===
Converted to C# for Fortnite by SL-x-TnT, original source code available at
https://github.com/powzix/ooz.
Copyright (C) 2016, Powzix
This program is free software: ... GNU General Public License ... version 3 ...
```

So GPLv3-headed derived code is distributed under an MIT package file, and the
upstream it derives from (`powzix/ooz`) has no LICENSE file at all. That
conflict is not this project's to resolve, but it is this project's to know
about: **building the decoder for local use is one thing; redistributing the
binary is another**, and nobody should ship `vrf-positions.exe` without
settling it. Building from source on the machine that uses it avoids the
question entirely, which is what `runners\build-decoder.bat` does and why
`vendor/parser/` is a drop-in rather than something committed here.

Worth recording alongside it, since it is the reason this project did not take
the decompressor when it took the parser: OozSharp implements **Mermaid only,
and within Mermaid only the raw/memcpy chunk path**. `Kraken.cs` contains no
Huffman and no TANS decoder, and seven paths raise `NotImplementedException`,
`DecodeBytes` among them. It works on these captures -- all 21 supported
captures in the reference library decode through it -- but it is a partial
decoder, it is slower than the native `oo2core`, and decompression was never
where the time went. `docs/valorant-replay-parser-features.md` has the numbers.

The predecessor `michel-giehl/ValorantReplayParserPlayground` is itself a fork
of `Shiqan/FortniteReplayDecompressor`; nothing is taken from either by hand.

---

## The bundled typefaces

`web/src/fonts/` contains four font files, committed rather than fetched, so
that the browser interface renders identically with no network -- which is the
usual state of a tool that reads captures off a local disk. All three families
are licensed under the **SIL Open Font License, Version 1.1**, whose full text
is reproduced in `web/src/fonts/OFL.txt` beside the files themselves, as that
licence requires.

| File | Family | Copyright |
|---|---|---|
| `PlusJakartaSans.woff2` | Plus Jakarta Sans (variable, 200..800) | Copyright (c) 2020 The Plus Jakarta Sans Project Authors, https://github.com/tokotype/PlusJakartaSans |
| `BarlowCondensed-600.woff2`, `BarlowCondensed-700.woff2` | Barlow Condensed | Copyright (c) 2017 The Barlow Project Authors, https://github.com/jpt/barlow |
| `JetBrainsMono.woff2` | JetBrains Mono (variable, 100..800) | Copyright (c) 2020 The JetBrains Mono Project Authors, https://github.com/JetBrains/JetBrainsMono |

All four are the latin subset as served by Google Fonts. The OFL permits
bundling and redistribution; it forbids selling the fonts on their own and
requires that any derivative be renamed. Neither applies here -- the files are
unmodified and are used only to render this project's own interface.

---

## @phosphor-icons/react

`web/package.json` lists `@phosphor-icons/react`, which is installed from npm
and is **not** vendored into this repository -- so this entry is a note rather
than a licence reproduction. It is MIT-licensed -- *Copyright (c) 2020 Phosphor
Icons*, verified from `node_modules/@phosphor-icons/react/LICENSE` rather than
assumed -- and the glyphs it draws are inlined into `web/dist/static/` at build
time. Only the forty-five `views/icons.tsx` imports by name are, each from its
own module: the package ships some three thousand.

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
drawn by `scripts/make_icons.py` and belong to this project; the browser
interface does not use them, and draws Phosphor's instead.

The wordmark in `web/src/views/icons.tsx` and the favicon in
`web/public/favicon.svg` are this project's own, and are deliberately not a
Riot mark.
