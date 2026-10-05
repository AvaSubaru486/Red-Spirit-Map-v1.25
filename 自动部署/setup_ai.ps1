[CmdletBinding()]
param([switch]$SkipDownload,[switch]$Isolated,[int]$Port=18090)
$ErrorActionPreference='Stop'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$Root=Split-Path -Parent $PSScriptRoot
$Ai=Join-Path $Root 'local-ai'
$Logs=Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Force -Path $Ai,$Logs | Out-Null
$State=Join-Path $Logs 'ai-state.json'
$SetupLock=$null
try { $SetupLock=[IO.File]::Open((Join-Path $Ai 'setup.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None) }
catch { Write-Host 'Local model setup is already running.'; exit 2 }
function Report($Phase,$Message,$Percent=0) {
 @{phase=$Phase;message=$Message;percent=$Percent;updated=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $State -Encoding UTF8
 Write-Host "[AI] $Message"
}
function JsonGet($Url) {
 $BundledPython=Join-Path $Root 'runtime\python.exe'
 if(Test-Path -LiteralPath $BundledPython) {
  $Json=& $BundledPython (Join-Path $PSScriptRoot 'ai_download.py') --json $Url
  if($LASTEXITCODE -ne 0) { throw "Official metadata download failed: $Url" }
  return ($Json -join "`n") | ConvertFrom-Json
 }
 for($Attempt=1;$Attempt -le 3;$Attempt++) {
  try {
   $Options=@{Uri=$Url;TimeoutSec=30;Headers=@{'User-Agent'='RedMap-LocalAI/1.1'}}
   if($Attempt -eq 2) { $Options.Proxy='http://127.0.0.1:7897' }
   return Invoke-RestMethod @Options
  }
  catch { if($Attempt -eq 3) { throw }; Start-Sleep -Seconds 2 }
 }
}
function Download($Url,$Path,$Hash,$Size) {
 if((Test-Path -LiteralPath $Path) -and ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -eq $Hash)) { return }
 if($SkipDownload) { throw "Missing verified file: $Path" }
 $BundledPython=Join-Path $Root 'runtime\python.exe'
 if(Test-Path -LiteralPath $BundledPython) {
  & $BundledPython (Join-Path $PSScriptRoot 'ai_download.py') --download $Url $Path $Hash $Size
  if($LASTEXITCODE -ne 0) { throw "Verified download failed: $Url" }
  return
 }
 $Temp="$Path.part"
 for($Attempt=1;$Attempt -le 3;$Attempt++) {
  try {
   Report 'download' "Download attempt $Attempt : $Url"
   $Client=New-Object Net.WebClient
   if($Attempt -eq 2) { $Client.Proxy=New-Object Net.WebProxy 'http://127.0.0.1:7897' }
   $Client.Headers.Add('User-Agent','RedMap-LocalAI/1.1')
   $Client.DownloadFileAsync([Uri]$Url,$Temp)
   $LastBytes=0
   $LastProgress=Get-Date
   while($Client.IsBusy) {
    Start-Sleep -Milliseconds 500
    $Bytes=if(Test-Path -LiteralPath $Temp) {(Get-Item -LiteralPath $Temp).Length} else {0}
    if($Bytes -gt $LastBytes) { $LastBytes=$Bytes; $LastProgress=Get-Date }
    if(((Get-Date)-$LastProgress).TotalSeconds -gt 90) { $Client.CancelAsync(); throw 'Download stalled for 90 seconds.' }
    $Percent=if($Size -gt 0) {[Math]::Min(99,[int](100*$Bytes/$Size))} else {0}
    Report 'download' ("Downloading {0:N1} / {1:N1} MB : {2}" -f ($Bytes/1MB),($Size/1MB),[IO.Path]::GetFileName($Path)) $Percent
   }
   if((Get-FileHash -LiteralPath $Temp -Algorithm SHA256).Hash -ne $Hash) { throw 'SHA256 mismatch' }
   Move-Item -LiteralPath $Temp -Destination $Path -Force
   $Client.Dispose()
   return
  } catch { if($Attempt -eq 3) { throw }; Start-Sleep -Seconds 2 }
 }
}
try {
 $ServerConfig=Join-Path $Ai 'server.json'
 $SavedPort=$Port
 if(Test-Path -LiteralPath $ServerConfig) { try { $SavedPort=(Get-Content -LiteralPath $ServerConfig -Raw | ConvertFrom-Json).port } catch {} }
 if(-not $Isolated) {
 foreach($ExistingPort in @($SavedPort,18090,1235,1234) | Select-Object -Unique) {
  try { $Existing=Invoke-RestMethod "http://127.0.0.1:$ExistingPort/v1/models" -TimeoutSec 2; if($Existing.data.Count -gt 0) {
   @{port=$ExistingPort;model=$Existing.data[0].id} | ConvertTo-Json | Set-Content -LiteralPath $ServerConfig -Encoding UTF8
   Report 'ready' "Local model ready at $ExistingPort" 100; exit 0
  } } catch {}
 }
 }
 $Drive=New-Object IO.DriveInfo ([IO.Path]::GetPathRoot($Root))
 if($Drive.AvailableFreeSpace -lt 4GB) { throw 'At least 4 GB free disk space is required.' }
 Report 'prepare' 'Reading official llama.cpp and Qwen metadata'
 $InstallManifest=Join-Path $Ai 'verified-install.json'
 if(Test-Path -LiteralPath $InstallManifest) {
  $Saved=Get-Content -LiteralPath $InstallManifest -Raw | ConvertFrom-Json
  $Asset=$Saved.asset
  $Meta=$Saved.model
 } else {
 $Release=JsonGet 'https://api.github.com/repos/ggml-org/llama.cpp/releases/latest'
 $Asset=$Release.assets | Where-Object { $_.name -match 'bin-win-cpu-x64.zip$' } | Select-Object -First 1
 if(-not $Asset) {
  $Releases=JsonGet 'https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=8'
  $Nightly=$Releases | Where-Object { @($_.assets | Where-Object {$_.name -match 'bin-win-cpu-x64.zip$'}).Count -gt 0 } | Select-Object -First 1
  if(-not $Nightly) { throw 'No official CPU runtime release found.' }
  $Tag=$Nightly.tag_name
  $Release=JsonGet "https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/$Tag"
  $Asset=$Release.assets | Where-Object { $_.name -match 'bin-win-cpu-x64.zip$' } | Select-Object -First 1
 }
 $Ms=JsonGet 'https://modelscope.cn/api/v1/models/Qwen/Qwen2.5-1.5B-Instruct-GGUF/repo/files?Revision=master&Recursive=true'
 $MsFile=$Ms.Data.Files | Where-Object { $_.Name -ieq 'qwen2.5-1.5b-instruct-q4_k_m.gguf' } | Select-Object -First 1
 if($MsFile.Sha256 -ne '6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e') { throw 'Qwen model digest differs from the reviewed official file.' }
 $Meta=@{sha=$MsFile.Revision;download_url="https://modelscope.cn/api/v1/models/Qwen/Qwen2.5-1.5B-Instruct-GGUF/repo?Revision=$($MsFile.Revision)&FilePath=$($MsFile.Path)";siblings=@(@{rfilename=$MsFile.Name;lfs=@{sha256=$MsFile.Sha256;size=$MsFile.Size}})}
 @{asset=$Asset;model=$Meta} | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $InstallManifest -Encoding UTF8
 }
 if(-not $Asset -or $Asset.digest -notmatch '^sha256:') { throw 'Official CPU runtime with SHA256 metadata unavailable.' }
 $Zip=Join-Path $Ai $Asset.name
 try { Download $Asset.browser_download_url $Zip ($Asset.digest.Substring(7)) $Asset.size }
 catch {
  Report 'download' 'Trying an alternate transport; official SHA256 verification remains mandatory'
  Download ("https://gh-proxy.com/"+$Asset.browser_download_url) $Zip ($Asset.digest.Substring(7)) $Asset.size
 }
 $Runtime=Join-Path $Ai 'runtime'
 Expand-Archive -LiteralPath $Zip -DestinationPath $Runtime -Force
 $Prerequisites=Join-Path $Ai 'prerequisites'
 $PrerequisiteManifest=Join-Path $Prerequisites 'manifest.json'
 if(Test-Path -LiteralPath $PrerequisiteManifest) {
  $PrerequisiteFiles=(Get-Content -LiteralPath $PrerequisiteManifest -Raw | ConvertFrom-Json).files
  foreach($Entry in $PrerequisiteFiles) {
   $Library=Join-Path $Prerequisites $Entry.name
   if((Get-FileHash -LiteralPath $Library -Algorithm SHA256).Hash -ne $Entry.sha256) { throw "C++ library SHA256 mismatch: $($Entry.name)" }
   Copy-Item -LiteralPath $Library -Destination (Join-Path $Runtime $Entry.name) -Force
  }
 }
 $ModelInfo=$Meta.siblings | Where-Object { $_.rfilename -ieq 'qwen2.5-1.5b-instruct-q4_k_m.gguf' } | Select-Object -First 1
 if(-not $ModelInfo.lfs.sha256) { throw 'Official model SHA256 metadata unavailable.' }
 $Models=Join-Path $Ai 'models'
 New-Item -ItemType Directory -Path $Models -Force | Out-Null
 $Model=Join-Path $Models $ModelInfo.rfilename
 $ModelUrl=if($Meta.download_url) {$Meta.download_url} else {"https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/$($Meta.sha)/$($ModelInfo.rfilename)"}
 Download $ModelUrl $Model $ModelInfo.lfs.sha256 $ModelInfo.lfs.size
 $Server=Get-ChildItem -LiteralPath $Runtime -Recurse -Filter llama-server.exe | Select-Object -First 1
 if(-not $Server) { throw 'Portable llama-server.exe is missing.' }
 $SelectedPort=$null
 foreach($Candidate in @($Port,18090,18091,18092,18093,18094,18095)) {
  $Listener=New-Object Net.Sockets.TcpListener ([Net.IPAddress]::Loopback),$Candidate
  try { $Listener.Start(); $SelectedPort=$Candidate; break } catch {} finally { $Listener.Stop() }
 }
 if(-not $SelectedPort) { throw 'No available local model server port.' }
 $Port=$SelectedPort
 @{port=$Port;model='redmap-qwen-local'} | ConvertTo-Json | Set-Content -LiteralPath $ServerConfig -Encoding UTF8
 Report 'loading' 'Loading Qwen local CPU model'
 $Process=Start-Process -FilePath $Server.FullName -ArgumentList @('-m',"`"$Model`"",'--host','127.0.0.1','--port',$Port,'-c','4096','--alias','redmap-qwen-local') -WorkingDirectory $Runtime -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $Logs 'llama-server.log') -RedirectStandardError (Join-Path $Logs 'llama-server-error.log')
 $Deadline=(Get-Date).AddMinutes(5)
 do {
  if($Process.HasExited) { throw 'Model server exited; inspect llama-server-error.log.' }
  try { $Health=Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 2; if($Health.status -eq 'ok') { break } } catch {}
  Start-Sleep -Seconds 2
 } while((Get-Date) -lt $Deadline)
 if($Health.status -ne 'ok') { throw 'Model loading timed out.' }
 Report 'verify' 'Verifying real local model chat'
 $Body=@{model='redmap-qwen-local';messages=@(@{role='user';content='Reply OK'});max_tokens=16} | ConvertTo-Json -Depth 5
 $Chat=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/chat/completions" -Method Post -ContentType 'application/json' -Body $Body -TimeoutSec 120
 if(-not $Chat.choices[0].message.content) { throw 'Local chat returned an empty answer.' }
 Report 'ready' 'Local model health and chat verified' 100
} catch { Report 'error' $_.Exception.Message; Write-Error $_; exit 1 }
finally { if($SetupLock) { $SetupLock.Dispose() } }
