@echo off
REM Serve the replay library and the web interface over HTTP.
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
REM Builds web/dist first: the server mounts it at / when it is there, so a stale
REM or missing bundle would be served instead of the current sources.
pushd "%~dp0.."
pushd web
REM `call`, or cmd hands control to npm.cmd and never returns to this script.
call npm run build
set "EXITCODE=%ERRORLEVEL%"
popd
if not "%EXITCODE%"=="0" (
    echo vrf-serve: web build failed, not starting the server.
    popd
    exit /b %EXITCODE%
)
uv run python scripts\vrf_serve.py %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
