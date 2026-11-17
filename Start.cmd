@echo off
setlocal
set "SLOTBOUND_PANEL=%~dp0slotbound_controls.pyw"
where pyw.exe >nul 2>&1
if errorlevel 1 goto pythonw
start "" pyw.exe -3 "%SLOTBOUND_PANEL%"
exit /b
:pythonw
where pythonw.exe >nul 2>&1
if errorlevel 1 goto msys
start "" pythonw.exe "%SLOTBOUND_PANEL%"
exit /b
:msys
set "SLOTBOUND_PYTHON=%SystemDrive%\msys64\ucrt64\bin\pythonw.exe"
if not exist "%SLOTBOUND_PYTHON%" goto missing
start "" "%SLOTBOUND_PYTHON%" "%SLOTBOUND_PANEL%"
exit /b
:missing
echo Install Python 3.10 or later with Tkinter. See README.md for setup.
pause
exit /b 1
