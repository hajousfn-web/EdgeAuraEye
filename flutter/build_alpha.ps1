$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Description,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    Write-Host "`n[$Description]" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

$flutterBat = $null
$flutterCommand = Get-Command flutter -ErrorAction SilentlyContinue
if ($flutterCommand) {
    $flutterBat = $flutterCommand.Source
}

if (-not $flutterBat) {
    $candidates = @(
        "C:\flutter\bin\flutter.bat",
        "C:\src\flutter\bin\flutter.bat",
        "D:\flutter\bin\flutter.bat",
        "$env:USERPROFILE\flutter\bin\flutter.bat",
        "$env:LOCALAPPDATA\flutter\bin\flutter.bat",
        "$env:FLUTTER_ROOT\bin\flutter.bat"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            $flutterBat = $candidate
            break
        }
    }
}

if (-not $flutterBat) {
    foreach ($path in @(where.exe flutter 2>$null)) {
        if (Test-Path -LiteralPath $path) {
            $flutterBat = $path
            break
        }
    }
}

if (-not $flutterBat) {
    throw "Flutter SDK was not found. Install Flutter or add its bin directory to PATH."
}

$flutterBin = Split-Path -Parent $flutterBat
$flutterRoot = Split-Path -Parent $flutterBin
$dartExe = Join-Path $flutterRoot "bin\cache\dart-sdk\bin\dart.exe"

if (-not (Test-Path -LiteralPath $dartExe)) {
    throw "Dart executable was not found at '$dartExe'. Run Flutter once to initialize its SDK."
}

$env:FLUTTER_ROOT = $flutterRoot
$env:Path = "$flutterBin;$flutterRoot\bin\cache\dart-sdk\bin;$env:Path"

$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot

Write-Host "Flutter SDK: $flutterRoot" -ForegroundColor Green
Write-Host "Project:     $projectRoot" -ForegroundColor Green

Invoke-Step "Resolving Flutter dependencies" {
    & $flutterBat pub get
}

Invoke-Step "Generating Drift database code" {
    & $dartExe run build_runner build --delete-conflicting-outputs
}

Invoke-Step "Building release APK" {
    & $flutterBat build apk --release
}

$apkPath = Join-Path $projectRoot "build\app\outputs\flutter-apk\app-release.apk"
if (-not (Test-Path -LiteralPath $apkPath)) {
    $apk = Get-ChildItem -Path (Join-Path $projectRoot "build") -Filter "*.apk" -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($apk) {
        $apkPath = $apk.FullName
    }
}

if (-not (Test-Path -LiteralPath $apkPath)) {
    throw "Build completed, but no APK was found under '$projectRoot\build'."
}

Write-Host "`nALPHA BUILD SUCCEEDED" -ForegroundColor Green
Write-Host "APK: $apkPath" -ForegroundColor Green
