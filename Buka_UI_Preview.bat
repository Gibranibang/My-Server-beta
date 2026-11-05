@echo off
title MyServer Companion UI Preview Server
echo Membuka server preview MyServer UI...
cd /d "D:\Projek\MyServer\Beta\MyServer Desktop Companion UI"
start http://localhost:8443
call npm.cmd run preview
pause
