$ErrorActionPreference = 'Stop'
$miniAppId = 'wxe3da273d4abca41e'
$sshKeyPath = 'C:\Users\Admin1\.ssh\genius_server.pem'

function Read-PrivateValue([string]$Prompt) {
    $secureValue = Read-Host -Prompt $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

Write-Host '密钥和测试手机号不会显示在屏幕上，也不会写入命令历史或发送到聊天。'
Write-Host '请输入患者端小程序 AppSecret 和您将用于微信登录测试的本人手机号。'
$miniSecret = Read-PrivateValue '患者端 AppSecret'
$testerPhone = Read-PrivateValue '测试手机号'
try {
    $payload = @{ appid = $miniAppId; secret = $miniSecret; phone = $testerPhone } | ConvertTo-Json -Compress
    $payload | ssh -i $sshKeyPath -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 ubuntu@140.143.125.233 'python3 /home/ubuntu/ChiHuiTong/current/scripts/stage-mini-customer-secret.py'
    if ($LASTEXITCODE -ne 0) { throw '安全录入未完成，请检查提示并联系开发人员。' }
} finally {
    $miniSecret = $null
    $testerPhone = $null
    $payload = $null
}
