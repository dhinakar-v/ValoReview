@echo off
REM Write the fixtures the Python and TypeScript models are compared against.
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
pushd "%~dp0.."
uv run python scripts\make_golden.py %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
