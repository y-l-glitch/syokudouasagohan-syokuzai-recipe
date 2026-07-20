@echo off
cd /d "%~dp0"
chcp 65001 >nul
echo ============================================
echo  レシピ検索ページの更新を開始します
echo ============================================
echo.
echo [1/2] 新着動画の字幕を取得中...(数分かかることがあります)
python collect.py
if errorlevel 1 (
  echo.
  echo !! 収集でエラーが発生しました。上のメッセージを確認してください。
  pause
  exit /b 1
)
echo.
echo [2/2] GitHub へアップロード中...
git add -A
git commit -m "update" >nul 2>&1
git push
if errorlevel 1 (
  echo.
  echo !! アップロードに失敗しました。ネット接続やGitHubのログインを確認してください。
  pause
  exit /b 1
)
echo.
echo ============================================
echo  完了！ 1〜2分後にページへ反映されます
echo ============================================
pause
