$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath (Join-Path $projectRoot 'backend')
try {
    & (Join-Path $projectRoot '.venv\Scripts\python.exe') -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw '백엔드 테스트 실패' }
} finally { Pop-Location }
Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
try {
    npm.cmd run typecheck
    if ($LASTEXITCODE -ne 0) { throw '타입 검사 실패' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw '프론트엔드 빌드 실패' }
    npm.cmd run test:e2e
    if ($LASTEXITCODE -ne 0) { throw '브라우저 테스트 실패' }
} finally { Pop-Location }
