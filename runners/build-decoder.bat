@echo off
REM Build the position decoder (csharp/VrfPositions).
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
REM
REM Needs the .NET 10 SDK and a clone of michel-giehl/ValorantReplayParser. The
REM clone is expected beside this repository; point somewhere else with:
REM     runners\build-decoder.bat -p:VrpRoot=D:\src\ValorantReplayParser
pushd "%~dp0.."
dotnet build csharp\VrfPositions\VrfPositions.csproj -c Release %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
