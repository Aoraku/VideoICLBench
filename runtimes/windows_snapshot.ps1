param([Parameter(Mandatory=$true)][string]$Workspace)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path $Workspace).Path
$files = Get-ChildItem -LiteralPath $root -File -Recurse | Where-Object { -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } | ForEach-Object {
    if ($_.Length -gt 16777216) { throw 'Task evidence exceeds the per-file limit' }
    @{ path = $_.FullName.Substring($root.Length).TrimStart('\'); size = $_.Length; modified = $_.LastWriteTimeUtc.ToString('o'); sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
}
$windows = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 } | ForEach-Object { @{ pid=$_.Id; title=$_.MainWindowTitle; name=$_.ProcessName } }
@{ files=@($files); windows=@($windows); culture=(Get-Culture).Name; short_date=(Get-Culture).DateTimeFormat.ShortDatePattern } | ConvertTo-Json -Depth 8
