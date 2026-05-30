@echo off
setlocal enabledelayedexpansion

echo === EnergyWise Benchmark Runner ===
echo.

if not exist reports mkdir reports

set MODE=sim
if "%1"=="--mode" (
    if "%2"=="native" set MODE=native
)

echo Mode: %MODE%
echo.

if "%MODE%"=="native" (
    set PLUGIN=
    if exist src\build\Release\EnergyWise.dll set PLUGIN=src\build\Release\EnergyWise.dll
    if exist src\build\EnergyWise.dll set PLUGIN=src\build\EnergyWise.dll
    if exist src\build\libEnergyWise.so set PLUGIN=src\build\libEnergyWise.so
    if exist src\build\libEnergyWise.dylib set PLUGIN=src\build\libEnergyWise.dylib

    if defined PLUGIN (
        for %%f in (testcases\*.c) do (
            echo --- %%f ---
            python3 src\energywise.py "%%f" --mode native --plugin "!PLUGIN!" --report "reports\%%~nf.json" --pretty
            if %errorlevel% neq 0 (
                python src\energywise.py "%%f" --mode native --plugin "!PLUGIN!" --report "reports\%%~nf.json" --pretty
            )
            echo.
        )
    ) else (
        echo Native plugin not found. Run build.bat first, or use sim mode.
        exit /b 1
    )
) else (
    for %%f in (testcases\*.c) do (
        echo --- %%f ---
        python3 src\energywise.py "%%f" --mode sim --report "reports\%%~nf.json" --pretty
        if %errorlevel% neq 0 (
            python src\energywise.py "%%f" --mode sim --report "reports\%%~nf.json" --pretty
        )
        echo.
    )
)

echo ================================================================
echo   SUMMARY COMPARISON TABLE
echo ================================================================

python3 -c "import json,os,glob;reports=sorted(glob.glob('reports/*.json'));rows=[];[rows.append((r['module'],sorted(r['functions'],key=lambda x:-x['total_nj'])[0]['name'],sorted(r['functions'],key=lambda x:-x['total_nj'])[0]['total_nj'],sorted(r['functions'],key=lambda x:-x['total_nj'])[1]['name'],sorted(r['functions'],key=lambda x:-x['total_nj'])[1]['total_nj'],(sorted(r['functions'],key=lambda x:-x['total_nj'])[0]['total_nj']-sorted(r['functions'],key=lambda x:-x['total_nj'])[1]['total_nj'])/sorted(r['functions'],key=lambda x:-x['total_nj'])[0]['total_nj']*100)) for path in reports for r in [json.load(open(path))] if len(r['functions'])>=2];print();print(f\"{'Benchmark':<14} {'Naive fn':<20} {'Naive nJ':>14}  {'Optimised fn':<20} {'Optimised nJ':>14}  {'Saving':>8}\");print('-'*100);[print(f'{b:<14} {n:<20} {nj:>14,.0f}  {o:<20} {oj:>14,.0f}  {p:>7.1f}%') for b,n,nj,o,oj,p in rows];print()" 2>nul || python -c "import json,os,glob;reports=sorted(glob.glob('reports/*.json'));rows=[];[rows.append((r['module'],sorted(r['functions'],key=lambda x:-x['total_nj'])[0]['name'],sorted(r['functions'],key=lambda x:-x['total_nj'])[0]['total_nj'],sorted(r['functions'],key=lambda x:-x['total_nj'])[1]['name'],sorted(r['functions'],key=lambda x:-x['total_nj'])[1]['total_nj'],(sorted(r['functions'],key=lambda x:-x['total_nj'])[0]['total_nj']-sorted(r['functions'],key=lambda x:-x['total_nj'])[1]['total_nj'])/sorted(r['functions'],key=lambda x:-x['total_nj'])[0]['total_nj']*100)) for path in reports for r in [json.load(open(path))] if len(r['functions'])>=2];print();print(f\"{'Benchmark':<14} {'Naive fn':<20} {'Naive nJ':>14}  {'Optimised fn':<20} {'Optimised nJ':>14}  {'Saving':>8}\");print('-'*100);[print(f'{b:<14} {n:<20} {nj:>14,.0f}  {o:<20} {oj:>14,.0f}  {p:>7.1f}%') for b,n,nj,o,oj,p in rows];print()"

echo ================================================================
echo   Reports saved to reports\
echo ================================================================