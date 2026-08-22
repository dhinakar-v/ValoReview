@echo off
REM Write the palette out as CSS custom properties, from vrfview/theme.py.
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
pushd "%~dp0.."
uv run python scripts\make_theme.py %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
