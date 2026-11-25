# Build Vigilo.exe (Windows, Python 3.11 64-bit).
#   powershell -ExecutionPolicy Bypass -File build.ps1
# Output: dist\Vigilo\Vigilo.exe and dist\Vigilo-<version>-win64.zip

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install -r requirements.txt pyinstaller
New-Item -ItemType Directory -Force build | Out-Null
python vigilo.py --make-icon build\vigilo.ico
python -m PyInstaller --noconfirm --distpath dist --workpath build\work vigilo.spec

# optional: NetSdk.dll for the experimental cloud connection (not part of the repository)
if (Test-Path sdk\NetSdk.dll) {
    New-Item -ItemType Directory -Force dist\Vigilo\sdk | Out-Null
    Copy-Item sdk\*.dll dist\Vigilo\sdk\
}

# license and documents next to Vigilo.exe, where people look for them
Copy-Item README.md, LICENSE, THIRD_PARTY_NOTICES.md, CHANGELOG.md dist\Vigilo\

$version = (Select-String -Path vigilo_app\common.py -Pattern 'APP_VERSION = "(.+)"').Matches[0].Groups[1].Value
# Python's zipfile, not Compress-Archive: Windows PowerShell 5.1 writes "\" in zip paths, against the format
python -c "import shutil; shutil.make_archive(r'dist\Vigilo-$version-win64', 'zip', 'dist', 'Vigilo')"
Write-Host "Done: dist\Vigilo\Vigilo.exe and dist\Vigilo-$version-win64.zip"
