param(
    [Parameter(Mandatory = $true)]
    [string[]]$Path,

    [switch]$RequireSigning
)

$ErrorActionPreference = "Stop"

function Find-SignTool {
    $fromPath = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($fromPath) {
        return $fromPath.Source
    }

    $kitsRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path $kitsRoot) {
        $candidate = Get-ChildItem -Path $kitsRoot -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "\\x64\\signtool.exe$" } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }

    return $null
}

$certPath = $env:RUFLOW_SIGN_CERT_PATH
$certPassword = $env:RUFLOW_SIGN_CERT_PASSWORD
$timestampUrl = if ($env:RUFLOW_TIMESTAMP_URL) { $env:RUFLOW_TIMESTAMP_URL } else { "http://timestamp.digicert.com" }

if (-not $certPath) {
    $message = "RUFLOW_SIGN_CERT_PATH is not set; skipping Authenticode signing."
    if ($RequireSigning) {
        throw $message
    }
    Write-Warning $message
    exit 0
}

if (-not (Test-Path -LiteralPath $certPath)) {
    throw "Signing certificate file was not found: $certPath"
}

$signtool = Find-SignTool
if (-not $signtool) {
    throw "signtool.exe was not found. Install Windows SDK or add signtool.exe to PATH."
}

foreach ($item in $Path) {
    if (-not (Test-Path -LiteralPath $item)) {
        throw "File to sign was not found: $item"
    }

    $args = @(
        "sign",
        "/fd", "SHA256",
        "/td", "SHA256",
        "/tr", $timestampUrl,
        "/f", $certPath
    )
    if ($certPassword) {
        $args += @("/p", $certPassword)
    }
    $args += $item

    & $signtool @args
    if ($LASTEXITCODE -ne 0) {
        throw "signtool failed for $item"
    }
}
