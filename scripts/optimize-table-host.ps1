param(
  [string]$Source = "3D/5c8a94ea-b4d5-4f7d-aed7-b94cd6f0a81b.glb",
  [string]$Output = "public/assets/actors/table-host.glb"
)

$ErrorActionPreference = 'Stop'
$sourcePath = (Resolve-Path -LiteralPath $Source).Path
$outputPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Output))
$workDir = Join-Path (Get-Location) 'output/table-host-optimize-work'
$sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourcePath).Hash
$npx = (Get-Command npx.cmd -ErrorAction Stop).Source
$ffmpeg = (Get-Command ffmpeg.exe -ErrorAction Stop).Source

function Invoke-Checked([string]$Command, [string[]]$Arguments) {
  & $Command @Arguments
  if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Command $Arguments" }
}

New-Item -ItemType Directory -Force -Path $workDir | Out-Null
New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($outputPath)) | Out-Null

$unpacked = Join-Path $workDir 'source.gltf'
$webp = Join-Path $workDir 'baseColor.webp'
$base = Join-Path $workDir 'base.glb'
$simple = Join-Path $workDir 'simple.glb'

Invoke-Checked $npx @('--yes', '@gltf-transform/cli', 'copy', $sourcePath, $unpacked)
$gltf = Get-Content -LiteralPath $unpacked -Raw | ConvertFrom-Json -Depth 100
if ($gltf.images.Count -ne 1 -or $gltf.textures.Count -ne 1) { throw 'Expected exactly one source texture.' }
$sourceImage = Join-Path $workDir $gltf.images[0].uri
Invoke-Checked $ffmpeg @('-y', '-i', $sourceImage, '-vf', 'scale=2048:2048:flags=lanczos', '-frames:v', '1', '-c:v', 'libwebp', '-quality', '88', '-compression_level', '6', $webp)

$gltf.images[0].uri = [System.IO.Path]::GetFileName($webp)
$gltf.images[0].mimeType = 'image/webp'
$gltf.textures[0].PSObject.Properties.Remove('source')
$gltf.textures[0] | Add-Member -NotePropertyName extensions -NotePropertyValue ([pscustomobject]@{
  EXT_texture_webp = [pscustomobject]@{ source = 0 }
}) -Force
$gltf | Add-Member -NotePropertyName extensionsUsed -NotePropertyValue @('EXT_texture_webp') -Force
$gltf | Add-Member -NotePropertyName extensionsRequired -NotePropertyValue @('EXT_texture_webp') -Force
$gltf | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $unpacked -Encoding utf8

Invoke-Checked $npx @('--yes', '@gltf-transform/cli', 'copy', $unpacked, $base)
Invoke-Checked $npx @('--yes', '@gltf-transform/cli', 'simplify', $base, $simple, '--ratio', '0.17', '--error', '0.0005', '--lock-border', 'true')
Invoke-Checked $npx @('--yes', '@gltf-transform/cli', 'meshopt', $simple, $outputPath, '--level', 'high', '--quantization-volume', 'mesh')
Invoke-Checked $npx @('--yes', '@gltf-transform/cli', 'validate', $outputPath)

$finalHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourcePath).Hash
if ($finalHash -ne $sourceHash) { throw 'Source GLB hash changed during optimization.' }
Write-Host "Created $outputPath"
Write-Host "Source SHA256: $sourceHash"
