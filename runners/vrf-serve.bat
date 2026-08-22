@echo off
REM Serve the replay library and the web interface over HTTP.
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
pushd "%~dp0.."
uv run python scripts\vrf_serve.py %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
