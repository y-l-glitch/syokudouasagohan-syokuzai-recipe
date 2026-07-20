@echo off
rem Task Scheduler silent update. For manual runs use the interactive bat.
cd /d "%~dp0"
echo ===== %date% %time% AUTO UPDATE START ===== >> update-log.txt
python collect.py >> update-log.txt 2>&1
git add -A
git commit -m "auto update" >> update-log.txt 2>&1
git push >> update-log.txt 2>&1
echo ===== %date% %time% AUTO UPDATE END ===== >> update-log.txt
