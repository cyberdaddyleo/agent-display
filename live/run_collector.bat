@echo off
cd /d C:\dsh\agent-display
"C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe" "C:\dsh\agent-display\live\collect_live.py" --loop 15 >> "C:\dsh\agent-display\live\collector.stdout.log" 2>> "C:\dsh\agent-display\live\collector.stderr.log"
