@echo off
REM Inspect a .vrf container: summary, events, players, chunks, blocks.
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
pushd "%~dp0.."
uv run vrf-reader %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
