# vendor/

Two drop-ins live here, and neither is committed.

An Oodle runtime, which every CLI that touches a compressed chunk finds:

    vendor/oo2core_9_win64.dll

And a published position decoder, if you would rather not keep a build tree:

    vendor/parser/vrf-positions.exe

The decoder is normally built instead, by `runners/build-decoder.bat`; see
README, "The decoder". Publish a self-contained one with:

    dotnet publish csharp/VrfPositions -c Release -r win-x64 --self-contained

Before handing that binary to anyone else, read the OozSharp section of
`THIRD_PARTY.md`: it links GPLv3-headed code shipped under an MIT package file.
That is fine to build and run locally, and redistributing it is fine on the
terms the same file's **Distribution** section sets out -- the decoder conveyed
under GPLv3 in its own folder, with a written offer of source, beside an
Apache-2.0 application it only ever talks to over argv. `runners\publish-decoder.bat`
is what produces the binary that offer refers to.

`.gitignore` keeps everything in this directory out of the repository except
this file. The DLL is Epic's intellectual property, licensed for redistribution
inside a licensed title rather than as a standalone download, so it is not
committed and never will be.

## Where to get one

Valorant cannot provide it. Its shipping exe links Oodle statically -- the
symbol `oo2::OodleLZ_Decompress` is compiled into `VALORANT-Win64-Shipping.exe`
-- and none of the 131 DLLs beside it is an `oo2core`. The exe's 659 exports are
all Wwise audio symbols, so there is no entry point to bind to either.

Any UE4/UE5 game install has one, usually at:

    <game>\Engine\Binaries\ThirdParty\Oodle\Win64\oo2core_9_win64.dll

Copy it here. Oodle 2.5 and later decode these blocks, so the version suffix
does not matter much; when several are present the highest number is used.

## Alternatives to this directory

    VRF_OODLE_DLL=C:\path\to\oo2core_9_win64.dll   in .env
    --oodle-dll C:\path\to\oo2core_9_win64.dll     on any CLI

If none of those is set, `libraries/oodlefind.py` scans the Steam and Epic
libraries for an installed game that ships one, and caches what it finds.
