# Build an MSIX package from the onedir PyInstaller output.
#
#   pwsh packaging/build_msix.ps1 -AppDir dist-onedir/Kataware -OutFile out/Kataware.msix `
#        -IdentityName <from Partner Center> -Publisher "CN=..." -PublisherDisplayName kyonccc
#
# Without -PfxFile the package is left unsigned: that is what Partner Center
# expects (the Store signs it). With -PfxFile it is signed for local testing.
param(
    [Parameter(Mandatory)] [string] $AppDir,
    [Parameter(Mandatory)] [string] $OutFile,
    [Parameter(Mandatory)] [string] $IdentityName,
    [Parameter(Mandatory)] [string] $Publisher,
    [Parameter(Mandatory)] [string] $PublisherDisplayName,
    [string] $Version,
    [string] $PfxFile,
    [string] $PfxPassword
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not $Version) {
    $init = Get-Content (Join-Path $root "src/kataware/__init__.py") -Raw
    if ($init -notmatch '__version__ = "(\d+)\.(\d+)\.(\d+)"') { throw "version not found" }
    $Version = "$($Matches[1]).$($Matches[2]).$($Matches[3]).0"   # MSIX needs four parts
}

# Newest Windows SDK that actually contains makeappx.exe (bin\<version>\x64\makeappx.exe)
$tool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\10.*\x64\makeappx.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [version]$_.Directory.Parent.Name } -Descending | Select-Object -First 1
if (-not $tool) { throw "Windows SDK (makeappx.exe) not found" }
$makeappx = $tool.FullName
$signtool = Join-Path $tool.DirectoryName "signtool.exe"
Write-Host "Using $makeappx"

$stage = Join-Path ([System.IO.Path]::GetTempPath()) ("kataware-msix-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $stage | Out-Null
Copy-Item -Recurse $AppDir (Join-Path $stage "Kataware")
Copy-Item -Recurse (Join-Path $root "packaging/build-icons/msix") (Join-Path $stage "Assets")

$manifest = Get-Content (Join-Path $root "packaging/msix/AppxManifest.xml.in") -Raw -Encoding utf8
$manifest = $manifest.Replace("@IDENTITY_NAME@", [Security.SecurityElement]::Escape($IdentityName)).
                      Replace("@PUBLISHER@", [Security.SecurityElement]::Escape($Publisher)).
                      Replace("@PUBLISHER_DISPLAY_NAME@", [Security.SecurityElement]::Escape($PublisherDisplayName)).
                      Replace("@VERSION@", $Version)
[System.IO.File]::WriteAllText((Join-Path $stage "AppxManifest.xml"), $manifest, [System.Text.UTF8Encoding]::new($false))

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutFile) | Out-Null
& $makeappx pack /o /d $stage /p $OutFile
if ($LASTEXITCODE -ne 0) { throw "makeappx failed ($LASTEXITCODE)" }

if ($PfxFile) {
    & $signtool sign /fd SHA256 /f $PfxFile /p $PfxPassword $OutFile
    if ($LASTEXITCODE -ne 0) { throw "signtool failed ($LASTEXITCODE)" }
}
Remove-Item -Recurse -Force $stage
Write-Host "MSIX written: $OutFile (version $Version, identity $IdentityName, publisher $Publisher)"
