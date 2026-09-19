[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$SecretFile,

    [string]$CoordinatorHost = 'kitling@192.168.1.121',
    [string]$RemoteScript = '/home/kitling/bin/bigqmt-enroll-fact-host.sh'
)

$ErrorActionPreference = 'Stop'

function Get-FactIdentityMetadata([string]$Path) {
    $document = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($document.schema_version -ne 1 -or $null -eq $document.hosts -or @($document.hosts).Count -ne 1) {
        throw 'Secret must contain exactly one schema_version=1 Host Agent identity.'
    }
    $identity = @($document.hosts)[0]
    $hostId = [string]$identity.host_id
    $keyId = [string]$identity.key_id
    if ([string]::IsNullOrWhiteSpace($hostId) -or [string]::IsNullOrWhiteSpace($keyId)) {
        throw 'Secret identity lacks host_id or key_id.'
    }
    if ($hostId -match '^(192\.0\.2\.|198\.51\.100\.)') {
        throw 'Test-net placeholder host_id is rejected.'
    }
    if ([string]::IsNullOrWhiteSpace([string]$identity.secret_b64)) {
        throw 'Secret identity lacks secret_b64.'
    }
    return [pscustomobject]@{ HostId = $hostId; KeyId = $keyId }
}

$metadata = Get-FactIdentityMetadata -Path $SecretFile
$scriptRoot = Split-Path -Parent $PSScriptRoot
$linuxScript = Join-Path $scriptRoot 'coordinator\enroll_shadow_fact_secret.sh'
if (-not (Test-Path -LiteralPath $linuxScript -PathType Leaf)) {
    throw "Missing enrollment script: $linuxScript"
}

$safeKeyId = $metadata.KeyId -replace '[^A-Za-z0-9_-]', '-'
$remoteDir = '/home/kitling/.local/share/bigqmt-fact-staging'
$remoteSecret = "$remoteDir/$safeKeyId.json"
$remoteUpload = '/home/kitling/.local/share/bigqmt-enroll-shadow-fact.sh'

Write-Host "Preparing facts-only enrollment for host_id=$($metadata.HostId), key_id=$($metadata.KeyId)."
Write-Host 'The HMAC Secret is transferred directly to .121. Its value is never printed.'

& ssh $CoordinatorHost "mkdir -p $remoteDir && chmod 700 $remoteDir"
if ($LASTEXITCODE -ne 0) { throw 'Cannot create protected staging directory on Coordinator.' }

& scp -q -- $linuxScript "${CoordinatorHost}:$remoteUpload"
if ($LASTEXITCODE -ne 0) { throw 'Cannot upload enrollment script to Coordinator.' }

& ssh $CoordinatorHost "sudo install -o root -g root -m 700 $remoteUpload $RemoteScript && rm -f $remoteUpload"
if ($LASTEXITCODE -ne 0) { throw 'Cannot install enrollment script on Coordinator.' }

& scp -q -- $SecretFile "${CoordinatorHost}:$remoteSecret"
if ($LASTEXITCODE -ne 0) { throw 'Cannot transfer Fact Secret to Coordinator staging directory.' }

& ssh $CoordinatorHost "chmod 600 $remoteSecret && sudo bash $RemoteScript $remoteSecret"
if ($LASTEXITCODE -ne 0) {
    throw 'Enrollment failed. The staged copy remains on .121 for protected operator inspection; do not copy it to NAS, Git, or chat.'
}

Write-Host "Fact identity enrolled: host_id=$($metadata.HostId), key_id=$($metadata.KeyId)."
