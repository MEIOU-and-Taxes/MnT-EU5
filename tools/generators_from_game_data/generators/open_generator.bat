@echo off
rem Opens one generator window. The launchers in the tools folder call this with provisions or buildings.
rem It needs Python 3 with tkinter. When there is none, it offers to install Python.
setlocal
set "GUI=%~dp0generators_gui.pyw"
set "TOOL=%~1"
set "USER_PY=%LOCALAPPDATA%\Programs\Python\Python312"

call :try py pyw && exit /b 0
call :try python pythonw && exit /b 0
call :try "%USER_PY%\python.exe" "%USER_PY%\pythonw.exe" && exit /b 0

echo.
echo  MnT Generators needs Python 3 with tkinter, and this computer has none.
echo.
where winget >nul 2>nul
if errorlevel 1 goto manual
choice /c YN /m " Install Python 3.12 now (about 30 MB, no admin rights needed)"
if errorlevel 2 goto manual
winget install --exact --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call :try "%USER_PY%\python.exe" "%USER_PY%\pythonw.exe" && exit /b 0
call :try py pyw && exit /b 0
echo.
echo  Python is installed, but this window cannot see it yet. Double-click the launcher again.
pause
exit /b 1

:manual
echo.
echo  Install Python 3 from https://www.python.org/downloads/ and keep "tcl/tk and IDLE" ticked.
echo  Then double-click the launcher again.
pause
exit /b 1

rem %1 checks for tkinter with console output, %2 opens the window without a console.
:try
%~1 -c "import tkinter" >nul 2>nul || exit /b 1
rem Pillow shows the game icons. Without it the window shows names only.
%~1 -c "import PIL" >nul 2>nul || %~1 -m pip install --user --quiet pillow >nul 2>nul
start "" %2 "%GUI%" %TOOL%
exit /b 0
