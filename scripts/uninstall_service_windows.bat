@echo off
title Media Downloader -- Uninstall

echo.
echo  Stopping and removing Media Downloader...
echo.

schtasks /end /tn "MediaDownloader" >nul 2>&1
schtasks /delete /tn "MediaDownloader" /f
netsh advfirewall firewall delete rule name="MediaDownloader" >nul 2>&1

echo.
echo  Done. Your .env file and media library were not touched.
echo.
pause
