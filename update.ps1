Set-Location $PSScriptRoot
Write-Host "============================================"
Write-Host " レシピ検索ページの更新を開始します"
Write-Host "============================================"
Write-Host ""
Write-Host "[1/2] 新着動画の字幕を取得中...(数分かかることがあります)"
python collect.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "!! 収集でエラーが発生しました。上のメッセージを確認してください。"
    exit 1
}
Write-Host ""
Write-Host "[2/2] GitHub へアップロード中..."
git add -A
git commit -m "update" *> $null
git push
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "!! アップロードに失敗しました。ネット接続やGitHubのログインを確認してください。"
    exit 1
}
Write-Host ""
Write-Host "============================================"
Write-Host " 完了！ 1〜2分後にページへ反映されます"
Write-Host "============================================"
