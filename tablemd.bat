@echo off
setlocal

if "%~1"=="" (
  echo Usage: tablemd.bat ^<TABLE_NAME or LIKE pattern^>
  echo Example: tablemd.bat TXD2BV01  ^|  tablemd.bat ABC%%
  exit /b 1
)

REM Run via Poetry virtualenv
poetry run python tablemd.py "%~1"

endlocal
