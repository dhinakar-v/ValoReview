@echo off
REM The packaged desktop backend, run from a checkout.
REM
REM    runnersrf-desktop.bat serve --port 8123
REM    runnersrf-desktop.bat fetch-assets --out %%LOCALAPPDATA%%\ValoReviewssets
REM
REM One argv switch over vrf-serve and fetch-assets, because a frozen bundle has
REM one executable and the desktop shell needs both.  `serve` is the default.
pushd "%~dp0.."
uv run python scriptsrf_desktop.py %*
set "EXITCODE=%ERRORLEVEL%"
popd
exit /b %EXITCODE%
