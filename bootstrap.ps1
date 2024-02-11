<#
.DESCRIPTION
    Script to install python and start the build.py.
#>

# About preference variables: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_preference_variable
# Stop execution on first non-terminating error (an error that doesn't stop the cmdlet processing)
$ErrorActionPreference = "Stop"

###################################################################################################
# Configuration
###################################################################################################
$config = @{
    # Required Python version - major.minor (e.g. 3.11)
    pythonVersion = "3.11"
    # Scoop install script
    scoopInstaller = "https://raw.githubusercontent.com/ScoopInstaller/Install/master/install.ps1"
}

###################################################################################################
# Utility functions
###################################################################################################

Function Edit-Env {
    # workaround for GithubActions
    if ($Env:USER_PATH_FIRST -eq "true") {
        $Env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    }
    else {
        $Env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    }
}

Function Invoke-CommandLine {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingInvokeExpression', '', Justification = 'Usually this statement must be avoided (https://learn.microsoft.com/en-us/powershell/scripting/learn/deep-dives/avoid-using-invoke-expression?view=powershell-7.3), here it is OK as it does not execute unknown code.')]
    param (
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$CommandLine,
        [Parameter(Mandatory = $false, Position = 1)]
        [bool]$StopAtError = $true,
        [Parameter(Mandatory = $false, Position = 2)]
        [bool]$Silent = $false
    )
    if (-Not $Silent) {
        Write-Output "Executing: $CommandLine"
    }
    $global:LASTEXITCODE = 0
    Invoke-Expression $CommandLine
    if ($global:LASTEXITCODE -ne 0) {
        if ($StopAtError) {
            Write-Error "Command line call `"$CommandLine`" failed with exit code $global:LASTEXITCODE"
        }
        else {
            if (-Not $Silent) {
                Write-Output "Command line call `"$CommandLine`" failed with exit code $global:LASTEXITCODE, continuing ..."
            }
        }
    }
}

Function Install-Scoop {
    # Initial Scoop installation
    if (-Not (Get-Command 'scoop' -ErrorAction SilentlyContinue)) {
        $tempFile = New-TemporaryFile
        Invoke-RestMethod $config.scoopInstaller -OutFile $tempFile.FullName
        if ((New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            & $tempFile.FullName -RunAsAdmin
        }
        else {
            & $tempFile.FullName
        }
        Edit-Env
        Remove-Item $tempFile.FullName
    }

    # Install needed tools
    Invoke-CommandLine "scoop update"
    Invoke-CommandLine "scoop install lessmsi" -Silent $true

    # Some old tweak to get 7zip installed correctly
    Invoke-CommandLine "scoop config use_lessmsi $true" -Silent $true

    # Avoid deadlocks while updating scoop buckets
    Invoke-CommandLine "scoop config autostash_on_conflict $true" -Silent $true

    # Some prerequisites to install other packages
    Invoke-CommandLine "scoop install 7zip" -Silent $true
    Invoke-CommandLine "scoop install innounp" -StopAtError $false -Silent $true
    Invoke-CommandLine "scoop install dark" -Silent $true
    Edit-Env
}

###################################################################################################
# Main
###################################################################################################

# python executable name
$python = "python" + $config.pythonVersion.Replace(".", "")

# Check if scoop is installed
$scoopPath = (Get-Command scoop -ErrorAction SilentlyContinue).Source
if ($scoopPath -eq $null) {
    Write-Output "Scoop not found. Trying to install scoop ..."
    Install-Scoop
} else {
    Write-Output "Found scoop under $scoopPath."
}
# Check if python is installed
$pythonPath = (Get-Command $python -ErrorAction SilentlyContinue).Source
if ($pythonPath -eq $null) {
    Write-Output "$python not found. Try to install $python via scoop ..."
    # Install python
    Invoke-CommandLine "scoop install https://raw.githubusercontent.com/ScoopInstaller/Versions/master/bucket/$python.json"
    # Check if python is installed
} else {
    Write-Output "$python found in $pythonPath"
    # Extract the directory of python exe file and add it to PATH. It needs to be the first entry in PATH
    # such that this version is used when the user calls python and not python311
    $pythonDir = [System.IO.Path]::GetDirectoryName($pythonPath)
    Write-Output "Adding $pythonDir to PATH"
    $Env:Path += ";$pythonDir"
}

# Call the build.py if it exists with all provided arguments
$buildScript = Join-Path $PSScriptRoot "bootstrap.py"
if (Test-Path $buildScript) {
    Write-Output "Calling $buildScript ..."
    & $python $buildScript $args
}
