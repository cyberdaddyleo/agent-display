@echo off
cd /d C:\dsh\agent-display
"C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe" -m http.server 8123 --bind 0.0.0.0 >> "C:\dsh\agent-display\server.stdout.log" 2>> "C:\dsh\agent-display\server.stderr.log"
