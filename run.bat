@echo off
chcp 65001 >nul
"%LocalAppData%\Programs\Python\Python310\python.exe" "%~dp0changer.py" %*
pause
