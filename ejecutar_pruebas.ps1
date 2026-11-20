# Ejecuta todas las pruebas y guarda los logs como evidencia en evidencias\logs\
#   Uso (con el entorno virtual activado y PostgreSQL encendido):
#       .\ejecutar_pruebas.ps1
# Las capturas de las pruebas funcionales quedan en evidencias\funcionales\
# (Archivo sin tildes a proposito: Windows PowerShell 5.1 lo lee mal si las tiene.)

$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$logs = "evidencias\logs"
New-Item -ItemType Directory -Force $logs | Out-Null

$grupos = [ordered]@{
    "1_unitarias"   = @("expresiones.tests.test_vision", "expresiones.tests.test_sensibilidad")
    "2_integracion" = @("expresiones.tests.test_web")
    "3_funcionales" = @("expresiones.tests.test_funcional")
}

$resumen = @()
foreach ($nombre in $grupos.Keys) {
    $archivo = Join-Path $logs "$nombre.log"
    Write-Host ""
    Write-Host "=== Pruebas $nombre ===" -ForegroundColor Cyan
    $lineas = New-Object System.Collections.Generic.List[string]
    $lineas.Add("Fecha: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
    $comando = "python manage.py test " + ($grupos[$nombre] -join " ") + " -v 2 --noinput 2>&1"
    $lineas.Add("Comando: $comando")
    # cmd /c une la salida normal y la de errores sin que PowerShell la altere.
    cmd /c $comando | ForEach-Object { Write-Host $_; $lineas.Add($_) }
    if ($LASTEXITCODE -eq 0) { $estado = "OK" } else { $estado = "FALLO" }
    $lineas | Out-File $archivo -Encoding utf8
    $resumen += ("{0,-15} -> {1}" -f $nombre, $estado)
}

$resumen | Out-File (Join-Path $logs "resumen.txt") -Encoding utf8
Write-Host ""
Write-Host "=== Resumen ===" -ForegroundColor Cyan
$resumen | ForEach-Object { Write-Host $_ }
Write-Host "Logs en $logs ; capturas en evidencias\funcionales" -ForegroundColor Green
