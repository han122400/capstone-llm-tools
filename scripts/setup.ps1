$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 가상환경 생성 실패' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r 'backend\requirements.txt'
if ($LASTEXITCODE -ne 0) { throw '백엔드 의존성 설치 실패' }
Push-Location -LiteralPath 'frontend'
try {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw '프론트엔드 의존성 설치 실패' }
} finally { Pop-Location }
Write-Output '설치 완료. .env.example을 .env로 복사한 후 scripts\backend.ps1과 scripts\frontend.ps1을 별도 터미널에서 실행하세요.'
