@echo off
REM Write each map's wall lines out as a PNG beside its radar, from
REM vrfview/walls.py -- the same threshold the sight raycaster uses.
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
pushd "%~dp0.."
uv run python scripts\make_walls.py %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
