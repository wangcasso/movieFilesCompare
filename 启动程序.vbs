Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "python """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\video_dedup.py""", 1, False
