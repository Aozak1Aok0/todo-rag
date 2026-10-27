# 把 deploy/hf-static 的静态演示发布到 gh-pages 分支（GitHub Pages）
#
# 用法（在任意目录）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File deploy\gh-pages\publish.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File deploy\gh-pages\publish.ps1 -Force   # 覆盖远端历史
#
# 前置：当前在 main、工作区干净（先 commit 你的改动）。

param(
    [string]$Branch = "gh-pages",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$src  = Join-Path $root "deploy\hf-static"

Push-Location $root
try {
    if (git status --porcelain) {
        throw "工作区不干净：先 commit（或 stash）再发布。"
    }
    $current = git branch --show-current
    if ($current -ne "main") {
        throw "请先切回 main（当前：$current）。"
    }

    $tmp = Join-Path $env:TEMP ("todo-rag-gh-pages-" + [guid]::NewGuid().ToString("N").Substring(0, 6))
    New-Item -ItemType Directory -Force $tmp | Out-Null
    foreach ($f in @("index.html", "data.json", "screenshot.png")) {
        Copy-Item (Join-Path $src $f) $tmp -Force
    }
    New-Item -ItemType File -Path (Join-Path $tmp ".nojekyll") -Force | Out-Null

    git show-ref --verify --quiet "refs/heads/$Branch"
    if ($LASTEXITCODE -eq 0) {
        git branch -D $Branch | Out-Null
        Write-Host "已删除本地旧分支 $Branch"
    }

    git checkout --orphan $Branch
    git rm -rf .
    Copy-Item (Join-Path $tmp "*") . -Force
    # 只提交这 4 个文件：git rm 会把 .gitignore 也删掉，此时 git add -A 会把
    # node_modules / models / chroma_db / todos.db 全部卷进来（曾造成 133MB 的分支）
    $wanted = @("index.html", "data.json", "screenshot.png", ".nojekyll")
    git add -- $wanted
    $staged = @(git diff --cached --name-only)
    if ($staged.Count -ne $wanted.Count) {
        throw "暂存文件数量不对（$($staged.Count) 个）：$($staged -join ', ')"
    }
    git commit -m "docs: static demo (GitHub Pages)"

    if ($Force) {
        git push -u origin $Branch --force
    } else {
        git push -u origin $Branch
    }

    git checkout main
    Write-Host ""
    Write-Host "发布完成。下一步："
    Write-Host "  1) 仓库 Settings -> Pages -> Source: Deploy from a branch -> $Branch / (root)"
    Write-Host "  2) 打开 https://aozak1aok0.github.io/todo-rag/"
} finally {
    Pop-Location
}
