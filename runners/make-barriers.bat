@echo off
REM Write each map's round-start spawn barriers out as a PNG beside its radar,
REM from the committed table in libraries/vrfview/barriers.json. Pass --decode to
REM rebuild that table from the reference frames in features/map-barriers/.
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
pushd "%~dp0.."
uv run python scripts\make_barriers.py %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
