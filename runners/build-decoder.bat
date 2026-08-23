@echo off
REM Build the position decoder (csharp/VrfPositions).
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
REM
REM Needs the .NET 10 SDK and nothing else: the parser it compiles against is
REM vendored at csharp/parser, whose README records the provenance and the four
REM things that differ from upstream.
pushd "%~dp0.."
dotnet build csharp\VrfPositions\VrfPositions.csproj -c Release %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
