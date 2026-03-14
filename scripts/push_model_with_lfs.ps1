param(
  [string]$RemoteUrl = 'https://github.com/Bionic-AI-Solutions/Moonshine.git',
  [string]$Branch = 'add/streaming-model-full'
)

Set-Location $PSScriptRoot\..  # move to repo root (assumes script in scripts/)
Write-Host "Working directory: $(Get-Location)"

# Init git if needed
if (-not (Test-Path .git)) {
  Write-Host "Initializing git repository..."
  git init
}

# Configure remote
try {
  git remote remove origin 2>$null
} catch {}

git remote add origin $RemoteUrl 2>$null || Write-Host "Remote already exists or couldn't add."

# Install git-lfs
Write-Host "Ensuring git-lfs is installed and initialized..."
git lfs install 2>$null || Write-Host "git-lfs command may not be installed. Install git-lfs and re-run this script if needed."

# Track model folder with LFS
$gitattributesPath = '.gitattributes'
Write-Host "Adding Git LFS tracking for 'moonshine-streaming-medium/**'"
if (-not (Get-Content $gitattributesPath -ErrorAction SilentlyContinue | Select-String 'moonshine-streaming-medium')) {
  git lfs track "moonshine-streaming-medium/**"
}

# Show all files in the model folder with sizes (we list everything per request)
Write-Host "Listing all files in 'moonshine-streaming-medium' with sizes:"
$modelPath = Join-Path (Get-Location) 'moonshine-streaming-medium'
if (Test-Path $modelPath) {
  Get-ChildItem -Path $modelPath -Recurse -File | Sort-Object Length -Descending |
    ForEach-Object { Write-Host ("{0:N2} MB`t{1}" -f ($_.Length/1MB), $_.FullName) }
  $total = (Get-ChildItem -Path $modelPath -Recurse -File | Measure-Object -Property Length -Sum).Sum
  Write-Host "---TOTAL---"
  Write-Host ("{0:N2} MB total" -f ($total/1MB))
} else {
  Write-Host "Model folder not found at: $modelPath"
}

# Add everything
Write-Host "Staging files... (this may take time)"
git add -A

# Commit
if (-not (git diff --cached --quiet)) {
  git commit -m "chore(models): add full repository + moonshine-streaming-medium via Git LFS"
} else {
  Write-Host "Nothing to commit."
}

# Create and switch to branch
git checkout -B $Branch

# Push
Write-Host "Pushing branch $Branch to $RemoteUrl (this may take a long time)"
try {
  git push --set-upstream origin $Branch
  Write-Host "Push completed."
} catch {
  Write-Host "Push failed: $_"
  Write-Host "If push fails due to large files or authentication, please address the error shown above."
}

Write-Host "Done. Check the remote repository for branch: $Branch"
