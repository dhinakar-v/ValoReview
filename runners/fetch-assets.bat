@echo off
REM Download Valorant map, agent and ability art into assets/.
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
pushd "%~dp0.."
uv run python scripts\fetch_assets.py %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
