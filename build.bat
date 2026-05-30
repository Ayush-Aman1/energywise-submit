@echo off
setlocal enabledelayedexpansion

echo === EnergyWise Build Script ===
echo.

where python3 >nul 2>nul
if %errorlevel% neq 0 (
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo Python not found. Install Python 3 and add to PATH.
        exit /b 1
    )
    set PYTHON=python
) else (
    set PYTHON=python3
)

%PYTHON% -c "import yaml" >nul 2>nul
if %errorlevel% neq 0 (
    echo Installing Python dependency: pyyaml
    %PYTHON% -m pip install pyyaml
)

echo Python simulator: OK

where llvm-config >nul 2>nul
if %errorlevel% equ 0 (
    for /f "delims=" %%i in ('llvm-config --prefix') do set LLVM_PREFIX=%%i
    echo Found LLVM at !LLVM_PREFIX!

    if not exist src\build mkdir src\build

    cd src\build
    cmake -DLT_LLVM_INSTALL_DIR="!LLVM_PREFIX!" ..
    if %errorlevel% neq 0 (
        echo CMake configuration failed.
        cd ..\..
        exit /b 1
    )
    cmake --build . --config Release
    if %errorlevel% neq 0 (
        echo Build failed.
        cd ..\..
        exit /b 1
    )
    cd ..\..

    if exist src\build\Release\EnergyWise.dll (
        echo LLVM pass plugin: OK
        echo.
        echo Build complete.
        echo   - Simulator mode:  %PYTHON% src\energywise.py testcases\^<file^>.c
        echo   - Native mode:     %PYTHON% src\energywise.py --mode native testcases\^<file^>.c
    ) else if exist src\build\EnergyWise.dll (
        echo LLVM pass plugin: OK
        echo.
        echo Build complete.
        echo   - Simulator mode:  %PYTHON% src\energywise.py testcases\^<file^>.c
        echo   - Native mode:     %PYTHON% src\energywise.py --mode native testcases\^<file^>.c
    ) else (
        echo LLVM pass plugin: build attempted but library not found.
        echo The Python simulator will still work fully.
        echo.
        echo Build complete.
        echo   - Simulator mode:  %PYTHON% src\energywise.py testcases\^<file^>.c
    )
) else (
    echo LLVM not found. The Python simulator mode works without LLVM.
    echo.
    echo To enable native mode, install LLVM:
    echo   - Download from https://releases.llvm.org/
    echo   - Or: choco install llvm
    echo.
    echo Build complete.
    echo   - Simulator mode:  %PYTHON% src\energywise.py testcases\^<file^>.c
)

echo.
echo Run all benchmarks:  run.bat