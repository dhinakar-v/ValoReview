@echo off
REM Publish a self-contained position decoder (csharp/VrfPositions).
REM
REM Unlike build-decoder.bat, which leaves a framework-dependent .dll that
REM csharpdecode runs through `dotnet`, this writes a folder holding
REM vrf-positions.exe and its own copy of the .NET runtime.  That is what a
REM packaged app ships: the machine that runs it has no SDK.
REM
REM Default output is vendor\parser, which is where csharpdecode looks for a
REM published drop-in.  Pass -o <dir> to write somewhere else.
REM
REM PublishTrimmed is deliberately OFF.  The parser reflects over its descriptor
REM catalogue, so trimming fails at run time on some captures and not others --
REM never enable it without running tests/test_positions.py against the result.
REM
REM Before giving that binary to anybody, read the OozSharp section of
REM THIRD_PARTY.md: the decoder links GPLv3-headed code.
pushd "%~dp0.."
if "%~1"=="" (
  set "OUT=-o vendor\parser"
) else (
  set "OUT="
)
dotnet publish csharp\VrfPositions\VrfPositions.csproj -c Release -r win-x64 --self-contained true -p:PublishTrimmed=false -p:PublishSingleFile=false %OUT% %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
