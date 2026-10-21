@echo off
rem AGENT_DISPLAY_LIVE wrapper: PYTHONUTF8 + cwd live + singleton cleanup + collector loop
rem stdout -> NUL (avoid Task Scheduler pipe-buffer blocking), stderr -> live\collector.stderr.log
set PYTHONUTF8=1
cd /d C:\dsh\agent-display\live
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\dsh\agent-display\live\ensure_single_collector.ps1" >nul 2>&1
"C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe" collect_live.py --loop 15 >nul 2>>"C:\dsh\agent-display\live\collector.stderr.log"
