param(
    [switch]$KillExisting
)

$ErrorActionPreference = "Stop"

$backendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $backendRoot

$listeners = @()
try {
    $listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop
}
catch {
    $listeners = @()
}

if ($listeners.Count -gt 0) {
    foreach ($listener in $listeners) {
        $ownerProcess = $listener.OwningProcess
        $proc = Get-Process -Id $ownerProcess -ErrorAction SilentlyContinue
        $cmdLine = ""
        try {
            $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerProcess"
            $cmdLine = $cim.CommandLine
        }
        catch {
            $cmdLine = "<unavailable>"
        }

        Write-Output "port_8000_listener_pid=$ownerProcess"
        Write-Output "port_8000_listener_name=$($proc.ProcessName)"
        Write-Output "port_8000_listener_command=$cmdLine"

        if ($KillExisting) {
            Stop-Process -Id $ownerProcess -Force
            Write-Output "killed_pid=$ownerProcess"
        }
    }
}

$venvCandidates = @(
    "C:\banking-ai-agent\.venv\Scripts\python.exe",
    "C:\banking-ai-agent\backend\.venv\Scripts\python.exe"
)

$pythonExe = $null
foreach ($candidate in $venvCandidates) {
    if (Test-Path $candidate) {
        $pythonExe = $candidate
        break
    }
}

if (-not $pythonExe) {
    throw "No supported venv python found. Checked: $($venvCandidates -join ', ')"
}

Write-Output "runtime_backend_root=$backendRoot"
Write-Output "runtime_python=$pythonExe"
Write-Output "runtime_port=8000"

& $pythonExe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
