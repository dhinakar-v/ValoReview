@echo off
REM Lint the tree (config: ruff.toml).
REM Runs from the repo root regardless of where it is invoked from, forwards all
REM arguments, and propagates the child exit code.
pushd "%~dp0.."
uv run ruff check . %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
