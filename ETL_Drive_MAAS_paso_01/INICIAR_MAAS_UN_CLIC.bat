@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title MAAS ECOLOGIA 4 - INICIAR TODO

rem Coloca este archivo en la misma carpeta que 08_ejecutar_etl_maas.py.
rem Orden: ETL completo -> schedule cada hora -> Streamlit (navegador).
set "ETL_DIR=%~dp0"
set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
set "RUTA_GUARDADA=%ETL_DIR%ruta_streamlit_maas.txt"

if not exist "%ETL_DIR%08_ejecutar_etl_maas.py" (
    echo ERROR: falta 08_ejecutar_etl_maas.py en esta carpeta.
    goto :ERROR
)
if not exist "%ETL_DIR%09_programar_etl_maas.py" (
    echo ERROR: falta 09_programar_etl_maas.py en esta carpeta.
    goto :ERROR
)
if not exist "%PYTHON%" (
    echo ERROR: no se encontro Python 3.12 en:
    echo %PYTHON%
    echo Modifica la variable PYTHON del archivo si cambiaste su instalacion.
    goto :ERROR
)

rem Primero reutiliza la ruta que el usuario eligio en una ejecucion anterior.
set "APP_FILE="
if exist "%RUTA_GUARDADA%" (
    set /p "APP_FILE="<"%RUTA_GUARDADA%"
    if not exist "%APP_FILE%" set "APP_FILE="
)

rem Ruta habitual de la carpeta del dashboard.
if not defined APP_FILE if exist "%USERPROFILE%\Downloads\MAAS_STREAMLIT_V09_SEMAFOROS_ACCESOS\app_maas_4.py" set "APP_FILE=%USERPROFILE%\Downloads\MAAS_STREAMLIT_V09_SEMAFOROS_ACCESOS\app_maas_4.py"

rem Si se extrajo en otra subcarpeta de Descargas, busca el programa.
if not defined APP_FILE (
    for /f "usebackq delims=" %%F in (`powershell -NoProfile -Command "$p=Join-Path $env:USERPROFILE 'Downloads'; Get-ChildItem -LiteralPath $p -Filter 'app_maas_4.py' -File -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.FullName -like '*MAAS_STREAMLIT_V09_SEMAFOROS_ACCESOS*' } | Select-Object -First 1 -ExpandProperty FullName"`) do if not defined APP_FILE set "APP_FILE=%%F"
)

rem Si no esta en Descargas, permite elegir el archivo con una ventana.
if not defined APP_FILE (
    echo.
    echo Selecciona app_maas_4.py en la carpeta de tu dashboard de Streamlit.
    for /f "usebackq delims=" %%F in (`powershell -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $f=New-Object System.Windows.Forms.OpenFileDialog; $f.Title='Selecciona app_maas_4.py de MAAS'; $f.FileName='app_maas_4.py'; $f.InitialDirectory=[Environment]::GetFolderPath('UserProfile'); if($f.ShowDialog() -eq 'OK') { $f.FileName }"`) do if not defined APP_FILE set "APP_FILE=%%F"
)

if not defined APP_FILE (
    echo ERROR: no se selecciono la aplicacion Streamlit.
    goto :ERROR
)
if not exist "%APP_FILE%" (
    echo ERROR: no existe el archivo de Streamlit seleccionado.
    goto :ERROR
)
for %%F in ("%APP_FILE%") do set "APP_DIR=%%~dpF"
>"%RUTA_GUARDADA%" echo(%APP_FILE%

echo.
echo ==========================================================
echo    MAAS ECOLOGIA 4 - INICIO COMPLETO CON UN SOLO CLIC
echo ==========================================================
echo.
echo [1/3] Actualizando datos desde Drive hasta SQL Server...
"%PYTHON%" -u "%ETL_DIR%08_ejecutar_etl_maas.py" --ejecutar
if errorlevel 1 (
    echo.
    echo ERROR: el ETL fallo. No se inicia Streamlit con datos desactualizados.
    echo Revisa el detalle y la carpeta logs_etl.
    goto :ERROR
)

echo.
echo [2/3] Iniciando actualizaciones automaticas cada hora...
start "MAAS - ETL CADA HORA" /D "%ETL_DIR%" cmd /k ""%PYTHON%" -u "%ETL_DIR%09_programar_etl_maas.py""
if errorlevel 1 goto :ERROR

echo.
echo [3/3] Iniciando Streamlit...
start "MAAS - STREAMLIT" /D "%APP_DIR%" cmd /k ""%PYTHON%" -m streamlit run "%APP_FILE%" --server.headless=false"
if errorlevel 1 goto :ERROR

echo.
echo LISTO: Streamlit abrira tu navegador cuando el servidor este preparado.
echo Deja abiertas las ventanas del programador y de Streamlit.
echo Para evitar procesos duplicados, cierra los anteriores antes de usar este archivo.
timeout /t 5 >nul
exit /b 0

:ERROR
echo.
echo El inicio se detuvo. Corrige el error antes de intentarlo de nuevo.
pause
exit /b 1
