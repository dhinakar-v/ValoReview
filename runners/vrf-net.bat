@echo off
REM Decode the UE replication stream: calibrate, decode, actors, exports, replay.
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
pushd "%~dp0.."
uv run python scripts\vrf_net.py %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
