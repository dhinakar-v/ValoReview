@echo off
REM Draw the app's transport glyphs into assets/icons/.
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
pushd "%~dp0.."
uv run python scripts\make_icons.py %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
