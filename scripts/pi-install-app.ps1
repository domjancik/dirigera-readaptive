param(
    [string]$PiHost = "192.168.1.250",
    [string]$PiUser = "piadmin",
    [string]$RepoUrl = "https://github.com/domjancik/dirigera-readaptive.git",
    [string]$AppDir = "/opt/dirigera-readaptive",
    [string]$TokenPath = "/etc/dirigera-readaptive/token",
    [string]$RemoteBin = ""
)

$ErrorActionPreference = "Stop"

if (-not $RemoteBin) {
    $RemoteBin = "/home/$PiUser/bin"
}

$target = "$PiUser@$PiHost"

function Invoke-Pi {
    param([string]$Command)
    ssh $target $Command
}

Write-Host "Installing OS packages on $target..."
Invoke-Pi "sudo apt-get update && sudo apt-get install -y git python3 python3-venv python3-pip"

Write-Host "Installing or updating app checkout at $AppDir..."
Invoke-Pi "sudo install -d -m 755 -o $PiUser -g $PiUser $AppDir"
Invoke-Pi "if [ -d '$AppDir/.git' ]; then cd '$AppDir' && git fetch --prune && git reset --hard origin/main; elif [ -z `"`$(find '$AppDir' -mindepth 1 -maxdepth 1 -print -quit)`" ]; then git clone '$RepoUrl' '$AppDir'; else echo '$AppDir exists and is not an empty directory or git checkout.' >&2; exit 1; fi"
Invoke-Pi "sudo chown -R ${PiUser}:$PiUser '$AppDir'"

Write-Host "Creating virtualenv and installing Python dependencies..."
Invoke-Pi "python3 -m venv '$AppDir/.venv'"
Invoke-Pi "'$AppDir/.venv/bin/python' -m pip install --upgrade pip"
Invoke-Pi "'$AppDir/.venv/bin/python' -m pip install PyYAML requests websockets"

Write-Host "Installing default config if missing..."
Invoke-Pi "if [ ! -f '$AppDir/config.yaml' ]; then cp '$AppDir/config.rpi.example.yaml' '$AppDir/config.yaml'; fi"

Write-Host "Installing systemd units..."
Invoke-Pi "sudo install -m 644 '$AppDir/systemd/dirigera-readaptive.service' /etc/systemd/system/dirigera-readaptive.service"
Invoke-Pi "sudo install -m 644 '$AppDir/systemd/dirigera-computed-schedule.service' /etc/systemd/system/dirigera-computed-schedule.service"
Invoke-Pi "sudo install -m 644 '$AppDir/systemd/dirigera-computed-schedule.timer' /etc/systemd/system/dirigera-computed-schedule.timer"
Invoke-Pi "sudo install -m 644 '$AppDir/systemd/dirigera-panel.service' /etc/systemd/system/dirigera-panel.service"
Invoke-Pi "sudo install -d -m 755 /etc/systemd/journald.conf.d"
Invoke-Pi "sudo install -m 644 '$AppDir/systemd/dirigera-readaptive-journald.conf' /etc/systemd/journald.conf.d/dirigera-readaptive.conf"
Invoke-Pi "sudo systemctl daemon-reload"
Invoke-Pi "sudo systemctl restart systemd-journald.service"

Write-Host "Installing status helper scripts..."
Invoke-Pi "mkdir -p '$RemoteBin' && install -m 755 '$AppDir/scripts/pi'/dirigera-* '$RemoteBin/'"

Write-Host "Enabling services..."
Invoke-Pi "sudo systemctl enable dirigera-readaptive.service"
Invoke-Pi "sudo systemctl enable dirigera-computed-schedule.timer"
Invoke-Pi "sudo systemctl enable dirigera-panel.service"
Invoke-Pi "sudo systemctl restart dirigera-panel.service"

$tokenStatus = ssh $target "sudo test -s '$TokenPath'; echo `$?"
if ($tokenStatus.Trim() -eq "0") {
    Write-Host "Token file exists; starting services..."
    Invoke-Pi "sudo systemctl restart dirigera-readaptive.service"
    Invoke-Pi "sudo systemctl restart dirigera-computed-schedule.timer"
    Invoke-Pi "sudo systemctl start dirigera-computed-schedule.service"
} else {
    Write-Warning "Token file is missing or empty at $TokenPath. Seed it with scripts/pi-seed-token.ps1, then start services."
}

Write-Host "Install/update complete. Try:"
Write-Host "  ssh $target '$RemoteBin/dirigera-status'"
