@echo off

call conda create -n fetchez python=3.11
if errorlevel 1 goto fail

echo.
echo ======================================
echo Fetchez environment created successfully
echo ======================================
echo.
echo To finish installation, run:
echo.
echo   conda activate fetchez
echo   python -m pip install fetchez
echo   fetchez --help
echo.
pause
exit /b 0

:fail
echo.
echo ERROR: Environment creation failed.
echo Make sure you are running from Anaconda Prompt.
echo.
pause
exit /b 1
