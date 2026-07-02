# Provision a MainDesk demo ECS instance via the Alibaba Cloud CLI.
# Prerequisites:
#   1. Alibaba Cloud CLI installed and on PATH (see docs/DEPLOY_ALIBABA_ECS.md)
#   2. `aliyun configure` has been run with an AccessKey pair that has
#      AliyunECSFullAccess + AliyunVPCFullAccess RAM permissions
#   3. Your $40 voucher is applied to the account
#
# What this script does:
#   - Creates a VPC + VSwitch in ap-southeast-1 (Singapore)
#   - Creates a security group with 22 (your IP only), 80, 443 (0.0.0.0/0)
#   - Creates a key pair and saves the private key locally
#   - Runs a single ecs.e-c1m2.large instance with Ubuntu 22.04
#   - Assigns a pay-by-traffic public IP
#   - Prints the SSH command when done
#
# All resources are tagged Project=maindesk so you can find + release them later.
# Pure ASCII intentionally: PS 5.1 mis-tokenizes some Unicode in no-BOM files.

$ErrorActionPreference = 'Stop'

# ============ CONFIG ============
$Region            = 'ap-southeast-1'
$InstanceType      = 'ecs.e-c1m2.large'
$ImageId           = 'ubuntu_22_04_x64_20G_alibase_20240220.vhd'
$SystemDiskSize    = 40
$KeyPairName       = 'maindesk-key'
$KeyOutPath        = "$HOME\.ssh\$KeyPairName.pem"
$SecurityGroupName = 'maindesk-sg'
$VpcName           = 'maindesk-vpc'
$VSwitchName       = 'maindesk-vsw'
$InstanceName      = 'maindesk-prod'
$Bandwidth         = 5
# ================================

function Say { param($msg) Write-Host "[provision] $msg" -ForegroundColor Cyan }
function Ali {
    param([string[]]$CmdArgs)
    $raw = aliyun @CmdArgs --RegionId $Region 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or $raw.TrimStart() -notmatch '^\{') {
        Write-Host "[aliyun error] args: $($CmdArgs -join ' ')" -ForegroundColor Red
        Write-Host $raw -ForegroundColor Red
        throw "aliyun call failed"
    }
    $raw | ConvertFrom-Json
}

# --- 0. sanity ---
Say "Checking CLI and credentials..."
$ver = aliyun version 2>&1
if ($LASTEXITCODE -ne 0) { throw "aliyun CLI not on PATH. See DEPLOY_ALIBABA_ECS.md." }
Say "aliyun $ver"

try { $MyIp = (Invoke-RestMethod https://api.ipify.org).Trim() } catch { $MyIp = '0.0.0.0' }
Say "Your public IP (for SSH allowlist): $MyIp"

# --- 1. VPC ---
Say "Creating VPC ($VpcName)..."
$vpc = Ali @('vpc','CreateVpc','--VpcName',$VpcName,'--CidrBlock','172.16.0.0/16')
$VpcId = $vpc.VpcId
Say "VPC $VpcId - waiting for Available..."
for ($i=0; $i -lt 30; $i++) {
    $s = Ali @('vpc','DescribeVpcAttribute','--VpcId',$VpcId)
    if ($s.Status -eq 'Available') { break }
    Start-Sleep -Seconds 2
}

# --- 2. VSwitch ---
Say "Creating VSwitch ($VSwitchName)..."
$zones = Ali @('ecs','DescribeZones')
$ZoneId = $zones.Zones.Zone[0].ZoneId
Say "Zone: $ZoneId"
$vsw = Ali @('vpc','CreateVSwitch','--VpcId',$VpcId,'--CidrBlock','172.16.1.0/24','--ZoneId',$ZoneId,'--VSwitchName',$VSwitchName)
$VSwitchId = $vsw.VSwitchId
for ($i=0; $i -lt 30; $i++) {
    $s = Ali @('vpc','DescribeVSwitchAttributes','--VSwitchId',$VSwitchId)
    if ($s.Status -eq 'Available') { break }
    Start-Sleep -Seconds 2
}

# --- 3. Security group + rules ---
Say "Creating security group ($SecurityGroupName)..."
$sg = Ali @('ecs','CreateSecurityGroup','--VpcId',$VpcId,'--SecurityGroupName',$SecurityGroupName,'--Description','MainDesk demo')
$SgId = $sg.SecurityGroupId
Say "Authorizing 22 (from $MyIp), 80, 443..."
Ali @('ecs','AuthorizeSecurityGroup','--SecurityGroupId',$SgId,'--IpProtocol','tcp','--PortRange','22/22','--SourceCidrIp',"$MyIp/32") | Out-Null
Ali @('ecs','AuthorizeSecurityGroup','--SecurityGroupId',$SgId,'--IpProtocol','tcp','--PortRange','80/80','--SourceCidrIp','0.0.0.0/0') | Out-Null
Ali @('ecs','AuthorizeSecurityGroup','--SecurityGroupId',$SgId,'--IpProtocol','tcp','--PortRange','443/443','--SourceCidrIp','0.0.0.0/0') | Out-Null

# --- 4. Key pair ---
Say "Creating key pair ($KeyPairName) -> $KeyOutPath"
if (Test-Path $KeyOutPath) {
    Write-Host "  Key file already exists locally. Skipping key creation." -ForegroundColor Yellow
} else {
    if (-not (Test-Path "$HOME\.ssh")) { New-Item -ItemType Directory "$HOME\.ssh" | Out-Null }
    $kp = Ali @('ecs','CreateKeyPair','--KeyPairName',$KeyPairName)
    $kp.PrivateKeyBody | Out-File -FilePath $KeyOutPath -Encoding ascii -NoNewline
    icacls $KeyOutPath /inheritance:r /grant:r "$($env:USERNAME):(R)" | Out-Null
    Say "Private key saved. Chmod-equivalent applied."
}

# --- 5. Run the instance ---
Say "Launching $InstanceType with $ImageId..."
$run = Ali @(
    'ecs','RunInstances',
    '--ImageId',$ImageId,
    '--InstanceType',$InstanceType,
    '--SecurityGroupId',$SgId,
    '--VSwitchId',$VSwitchId,
    '--InstanceName',$InstanceName,
    '--HostName',$InstanceName,
    '--SystemDisk.Category','cloud_essd_entry',
    '--SystemDisk.Size',"$SystemDiskSize",
    '--KeyPairName',$KeyPairName,
    '--InstanceChargeType','PostPaid',
    '--InternetChargeType','PayByTraffic',
    '--InternetMaxBandwidthOut',"$Bandwidth",
    '--Amount','1',
    '--Tag.1.Key','Project','--Tag.1.Value','maindesk'
)
$InstanceId = $run.InstanceIdSets.InstanceIdSet[0]
Say "Instance $InstanceId launching. Waiting for Running state..."

$idsJson = '["' + $InstanceId + '"]'
$PublicIp = $null
for ($i=0; $i -lt 60; $i++) {
    $d = Ali @('ecs','DescribeInstances','--InstanceIds',$idsJson)
    $inst = $d.Instances.Instance[0]
    if ($inst.Status -eq 'Running') {
        $PublicIp = $inst.PublicIpAddress.IpAddress[0]
        break
    }
    Start-Sleep -Seconds 3
}

if (-not $PublicIp) { throw "Instance did not reach Running in 3 minutes. Check ECS console." }

# --- 6. Report ---
Write-Host ""
Write-Host "===========================================================" -ForegroundColor Green
Write-Host "  MainDesk ECS instance is up." -ForegroundColor Green
Write-Host "===========================================================" -ForegroundColor Green
Write-Host "  Instance ID : $InstanceId"
Write-Host "  Public IP   : $PublicIp"
Write-Host "  Region      : $Region"
Write-Host "  Key file    : $KeyOutPath"
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host "    ssh -i $KeyOutPath root@$PublicIp"
Write-Host "    curl -fsSL https://raw.githubusercontent.com/Otitodev/healthdesk-ai/main/deploy/bootstrap.sh -o bootstrap.sh"
Write-Host "    chmod +x bootstrap.sh && sudo ./bootstrap.sh"
Write-Host ""
Write-Host "  To release everything later:"
Write-Host "    aliyun ecs DeleteInstance --InstanceId $InstanceId --Force true --region $Region"
Write-Host "    aliyun ecs DeleteSecurityGroup --SecurityGroupId $SgId --region $Region"
Write-Host "    aliyun vpc DeleteVSwitch --VSwitchId $VSwitchId --region $Region"
Write-Host "    aliyun vpc DeleteVpc --VpcId $VpcId --region $Region"
Write-Host ""
