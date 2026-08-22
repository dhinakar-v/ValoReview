@echo off
REM Dump a whole .vrf replay to a single JSON document.
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
pushd "%~dp0.."
uv run vrf-to-json %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
