# check_exe.py
import sys
import os

# Tarkista exe-polku
exe_path = r"C:\Users\teemu.leisto.SYNERALLCIS\SubtitleMatcher\dist\SubtitleMatcher.exe"

if os.path.exists(exe_path):
    print(f"✅ Exe found: {exe_path}")
    print(f"   Size: {os.path.getsize(exe_path)} bytes")
    print(f"   Modified: {os.path.getmtime(exe_path)}")
else:
    print(f"❌ Exe not found")