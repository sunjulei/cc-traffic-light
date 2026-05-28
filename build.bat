@echo off
cd /d "%~dp0"
pyinstaller --onefile --windowed --name ClaudeTrafficLight --clean claude_traffic_light.py
echo.
if exist dist\ClaudeTrafficLight.exe (
    echo Build successful: dist\ClaudeTrafficLight.exe
) else (
    echo Build failed!
)
pause
