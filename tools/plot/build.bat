@echo off
setlocal enabledelayedexpansion
title Building MEIOU and Taxes Plotter

echo   MEIOU and Taxes Plotter - PyInstaller Build Script

:: Check for PyInstaller installation
python -c "import PyInstaller" 2>nul
if %ERRORLEVEL% neq 0 (
    echo [WARNING] PyInstaller is not installed in the active environment.
    echo [INFO] Installing PyInstaller and dependencies...
    pip install pyinstaller PyQt6 matplotlib seaborn pandas scikit-learn openpyxl
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install dependencies. Please check your Python/pip installation.
        goto fail
    )
)

:: Clean previous build artifacts
echo.
echo [INFO] Cleaning up old build/ and dist/ folders...
if exist "build" rd /s /q "build"
if exist "dist\MT_grapher" rd /s /q "dist\MT_grapher"

:: Run PyInstaller
echo.
echo [INFO] Building executable using MT_grapher.spec...
pyinstaller --clean MT_grapher.spec

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Build failed! Check the output above for details.
    goto fail
)

:: Copy extra runtime essentials into dist if not already there
echo.
echo [INFO] Verifying runtime dependencies in dist folder...
if exist "key_configs.json" copy /y "key_configs.json" "dist\MT_grapher\" >nul
if exist "locations.csv" copy /y "locations.csv" "dist\MT_grapher\" >nul
if exist "icon.png" copy /y "icon.png" "dist\MT_grapher\" >nul

echo.
echo [SUCCESS] Build completed successfully!
echo Binary output location: dist\MT_grapher\MT_grapher.exe
echo.
pause
exit /b 0

:fail
echo.
echo [FAILED] The build could not be completed.
pause
exit /b 1