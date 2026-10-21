@echo off
rem AGENT_DISPLAY_LIVE wrapper (v2): UTF-8 + cwd live + ???? + collector loop
rem stdout->NUL (? Task Scheduler ??????), stderr->live\collector.stderr.log
set PYTHONUTF8=1
cd /d C:\dsh\agent-display\live
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\dsh\agent-display\live\ensure_single_collector.ps1" >nul 2>&1
"C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe" collect_live.py --loop 15 >nul 2>>"C:\dsh\agent-display\live\collector.stderr.log"
