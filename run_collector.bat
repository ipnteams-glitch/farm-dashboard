@echo off
REM ASCII-only (Thai/parentheses break .bat). Loop collector every 30s.
cd /d "%~dp0"
python collector.py --loop 30
pause
