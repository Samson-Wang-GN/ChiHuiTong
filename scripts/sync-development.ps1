param(
    [string]$SshKey = 'C:\Users\Admin1\.ssh\genius_server.pem'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
function Assert-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE" }
}
$revision = (git -c "safe.directory=$projectRoot" rev-parse HEAD).Trim()
Assert-Exit 'Read local revision'
if ($revision -notmatch '^[0-9a-f]{40}$') { throw 'Invalid revision' }
$dirty = git -c "safe.directory=$projectRoot" status --porcelain
Assert-Exit 'Inspect local worktree'
if ($dirty) { throw 'Commit the reviewed project files before syncing; uncommitted files are not deployed' }
$packageDir = Join-Path $projectRoot '.tmp'
New-Item -ItemType Directory -Path $packageDir -Force | Out-Null
$packageName = "chihuitong-$revision.tar.gz"
$package = Join-Path $packageDir $packageName
git -c "safe.directory=$projectRoot" archive --format=tar.gz --output=$package HEAD
Assert-Exit 'Create committed source archive'
$checksum = (Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant()
$sshOptions = @('-i', $SshKey, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10')
$targetHost = 'ubuntu@140.143.125.233'
ssh @sshOptions $targetHost 'test "$(hostname)" = VM-0-12-ubuntu && mkdir -p /home/ubuntu/ChiHuiTong/incoming /home/ubuntu/ChiHuiTong/releases && chmod 700 /home/ubuntu/ChiHuiTong'
Assert-Exit 'Verify host and prepare isolated directories'
scp @sshOptions $package "${targetHost}:/home/ubuntu/ChiHuiTong/incoming/$packageName"
Assert-Exit 'Transfer committed source archive'
$remoteScript = @'
set -eu
root=/home/ubuntu/ChiHuiTong
test "$(hostname)" = VM-0-12-ubuntu
test "$(realpath "$root")" = "$root"
revision=__REVISION__
checksum=__CHECKSUM__
archive="$root/incoming/chihuitong-$revision.tar.gz"
printf '%s  %s\n' "$checksum" "$archive" | sha256sum -c -
test ! -e "$root/.git"
release="$root/releases/$revision"
if test -e "$release"; then
  test -f "$root/incoming/$revision.sha256"
  test "$(cat "$root/incoming/$revision.sha256")" = "$checksum"
else
  mkdir "$release"
  tar -xzf "$archive" -C "$release" --no-same-owner
  test ! -e "$release/.git"
  test -f "$release/AGENTS.md"
  test -f "$release/docs/requirements.md"
  printf '%s\n' "$checksum" > "$root/incoming/$revision.sha256"
fi
if test -e "$root/current" && ! test -L "$root/current"; then
  printf '%s\n' 'REFUSED: current is not a symlink' >&2
  exit 1
fi
if test -L "$root/current"; then
  readlink "$root/current" > "$root/incoming/previous-release.txt"
fi
ln -s "$release" "$root/current-$revision"
mv -Tf "$root/current-$revision" "$root/current"
printf 'SYNCED %s\n' "$revision"
test ! -e "$root/current/.git"
'@
$remoteScript = $remoteScript.Replace('__REVISION__', $revision).Replace('__CHECKSUM__', $checksum)
$remoteScript | ssh @sshOptions $targetHost 'tr -d "\r" | bash -s'
Assert-Exit 'Verify archive and activate source snapshot'
Write-Output "Synced commit $revision; no GitHub access or Git metadata on server. Tests must run remotely."
