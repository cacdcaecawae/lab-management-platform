<#
本机试用：在本机跑和服务器上同样的一套（Nginx + Gunicorn + PostgreSQL），外加 Mailpit 本机收件箱。
在仓库根目录的 PowerShell 里运行：

  powershell -ExecutionPolicy Bypass -File scripts\trial.ps1 up      构建并启动（第一次要几分钟）
  powershell -ExecutionPolicy Bypass -File scripts\trial.ps1 admin   新建运维账号（会问用户名、邮箱、密码）
  powershell -ExecutionPolicy Bypass -File scripts\trial.ps1 logs    查看日志，Ctrl+C 退出
  powershell -ExecutionPolicy Bypass -File scripts\trial.ps1 down    停止，数据保留
  powershell -ExecutionPolicy Bypass -File scripts\trial.ps1 reset   停止并删除全部试用数据（数据库和上传的文件）
#>
param([ValidateSet('up', 'admin', 'logs', 'down', 'reset')][string]$Action = 'up')
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root 'trial.env.local'
if (-not (Test-Path $envFile)) {
    $text = [IO.File]::ReadAllText((Join-Path $root 'infra\trial.env.example'))
    while ($text.Contains('__RANDOM__')) {
        $i = $text.IndexOf('__RANDOM__')
        $random = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
        $text = $text.Substring(0, $i) + $random + $text.Substring($i + '__RANDOM__'.Length)
    }
    [IO.File]::WriteAllText($envFile, $text)  # UTF-8 without BOM, which docker compose reads
    Write-Host "已生成 $envFile（密钥和数据库密码是随机的）"
}
$port = (Select-String -Path $envFile -Pattern '^HTTP_PORT=(\d+)').Matches[0].Groups[1].Value
$compose = @(
    'compose', '-f', (Join-Path $root 'infra\docker-compose.prod.yml'), '-f', (Join-Path $root 'infra\docker-compose.local.yml'),
    '--env-file', $envFile
)

function Invoke-Compose {
    docker @compose @args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Action) {
    'up' {
        Invoke-Compose up -d --build
        Write-Host '等待后端就绪……'
        $ready = $false
        for ($i = 0; $i -lt 60 -and -not $ready; $i++) {
            try {
                $ready = (Invoke-WebRequest "http://localhost:$port/api/auth/csrf/" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 204
            } catch {
                Start-Sleep -Seconds 2
            }
        }
        if (-not $ready) {
            Write-Host '后端两分钟内没有就绪，用 "scripts\trial.ps1 logs" 查看原因。'
            exit 1
        }
        Write-Host ''
        Write-Host "平台：      http://localhost:$port"
        Write-Host '本机收件箱：http://localhost:8025'
        Write-Host '第一次使用先新建运维账号：powershell -ExecutionPolicy Bypass -File scripts\trial.ps1 admin'
    }
    'admin' { Invoke-Compose exec backend python manage.py createsuperuser }
    'logs' { Invoke-Compose logs -f --tail 100 }
    'down' { Invoke-Compose down }
    'reset' {
        $answer = Read-Host '将删除试用的数据库和上传的文件，输入 yes 确认'
        if ($answer -ne 'yes') { Write-Host '已取消'; exit 0 }
        Invoke-Compose down -v
    }
}
