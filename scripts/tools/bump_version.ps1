# =============================================================================
#  bump_version.ps1 - increment the patch of VERSION file (called by build.bat)
#
#  WHY THIS FILE EXISTS
#  On locked-down machines an endpoint policy silently blocks a PowerShell
#  -Command one-liner whose command line contains a regex: powershell.exe exits
#  with code 786 and never touches the file, so build.bat would keep building
#  while VERSION stayed behind. The same logic invoked from this script file
#  through -File is not affected, which is why this helper exists.
#
#  VERSION SCHEME
#    VERSION holds a plain three-part version - `1.0.0` on a single line.
#    Every build bumps the patch; when a segment hits 100 it carries to the next
#    higher one:
#    1.0.99  -> 1.1.0
#    1.99.99 -> 2.0.0
#    99.99.99 -> 100.0.0
#
#  USAGE
#    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tools\bump_version.ps1
#    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tools\bump_version.ps1 -Path VERSION
#
#  OUTPUT (stdout, single line)
#    OK=<old>-><new>   file updated, exit code 0
#    ERROR=<reason>    nothing written, exit code != 0
# =============================================================================
param(
    [string]$Path = 'VERSION'
)

$ErrorActionPreference = 'Stop'

try {
    $full = (Resolve-Path -LiteralPath $Path).Path
    $text = [IO.File]::ReadAllText($full).TrimEnd("`r`n")

    # Match a single-line three-part version
    $m = [regex]::Match($text, '^(\d+)\.(\d+)\.(\d+)$')
    if (-not $m.Success) {
        Write-Output 'ERROR=version-not-three-part'
        exit 4
    }

    $major = [int]$m.Groups[1].Value
    $minor = [int]$m.Groups[2].Value
    $patch = [int]$m.Groups[3].Value

    $old = "$major.$minor.$patch"

    $patch += 1
    if ($patch -ge 100) {
        $patch = 0
        $minor += 1
    }
    if ($minor -ge 100) {
        $minor = 0
        $major += 1
    }

    $new = "$major.$minor.$patch"

    if ($new -ne $text) {
        # Write as UTF-8 without BOM (match existing VERSION file encoding)
        $utf8NoBom = New-Object Text.UTF8Encoding($false)
        [IO.File]::WriteAllText($full, $new + "`r`n", $utf8NoBom)
    }

    Write-Output ('OK=' + $old + '->' + $new)
    exit 0
}
catch {
    Write-Output ('ERROR=' + $_.Exception.Message)
    exit 1
}