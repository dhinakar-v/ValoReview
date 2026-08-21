@echo off
REM Open the 2D replay viewer, or dump replay state as text.
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
pushd "%~dp0.."
uv run python scripts\vrf_view.py %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
