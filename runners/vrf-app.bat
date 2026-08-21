@echo off
REM Browse the replay library (CustomTkinter match list).
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
pushd "%~dp0.."
uv run python scripts\vrf_app.py %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
