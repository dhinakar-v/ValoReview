@echo off
REM Run the test suite.
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
pushd "%~dp0.."
uv run pytest %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
