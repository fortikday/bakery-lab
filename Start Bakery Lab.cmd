@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 goto folder_error

py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 11))" >nul 2>&1
if errorlevel 1 goto try_python
set "BAKERY_PYTHON=py -3"
goto launch

:try_python
python -c "import sys; raise SystemExit(sys.version_info < (3, 11))" >nul 2>&1
if errorlevel 1 goto no_python
set "BAKERY_PYTHON=python"

:launch
%BAKERY_PYTHON% -c "import tkinter; tkinter.Tcl()" >nul 2>&1
if errorlevel 1 goto console_mode
%BAKERY_PYTHON% "%~dp0desktop.py"
if errorlevel 1 goto start_error
popd
exit /b 0

:console_mode
echo This Python installation cannot open the desktop window.
echo Opening the browser app instead. Keep this window open while using it.
%BAKERY_PYTHON% "%~dp0serve.py"
if errorlevel 1 goto start_error
popd
exit /b 0

:no_python
echo Bakery Lab's source download needs Python 3.11 or newer.
echo Install Python from https://www.python.org/downloads/ and try again.
echo A packaged Windows download can run without installing Python.
goto wait_and_exit

:folder_error
echo Bakery Lab could not open its project folder. Extract the entire ZIP first.
goto wait_and_exit

:start_error
echo Bakery Lab could not start. Please keep all project files together.
echo You can also try running python serve.py from this folder.

:wait_and_exit
pause
popd
exit /b 1
