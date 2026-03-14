Set-Location 'E:\Bionic AI\moonshine'
Write-Output '=== Top 100 largest files (MB) ==='
Get-ChildItem -Path 'moonshine-streaming-medium' -Recurse -File |
  Sort-Object Length -Descending |
  Select-Object -First 100 FullName,@{Name='SizeMB';Expression={[math]::Round($_.Length/1MB,2)}} |
  Format-Table -AutoSize

Write-Output "`n=== Model file types (onnx/safetensors/pt/bin) ==="
Get-ChildItem -Path 'moonshine-streaming-medium' -Recurse -File |
  Where-Object { $_.Extension -in '.onnx','.safetensors','.pt','.bin' } |
  Select-Object FullName,@{Name='SizeMB';Expression={[math]::Round($_.Length/1MB,2)}} |
  Format-Table -AutoSize

Write-Output "`n=== Total folder size (GB) ==="
$sum=(Get-ChildItem -Path 'moonshine-streaming-medium' -Recurse -File | Measure-Object Length -Sum).Sum
[math]::Round($sum/1GB,3)
