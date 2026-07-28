@echo off
echo Building SubtitleMatcher.exe...

REM remove old builds
rmdir /s /q build
rmdir /s /q dist

REM Build exe
pyinstaller --onefile --windowed --name SubtitleMatcher --icon=resources/icon.ico ui.py

echo Done!
pause