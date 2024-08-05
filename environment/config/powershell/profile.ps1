#Import-Module posh-git
#Import-Module oh-my-posh
#Set-Theme Paradox
oh-my-posh --init --shell pwsh --config $env:POSH_THEMES_PATH/jandedobbeleer.omp.json | Invoke-Expression

New-Alias k kubectl
New-Alias d docker
