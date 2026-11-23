' Starts 3zT Agent from this folder without a console window (the installer makes its own shortcut).
' Uses the bundled Python when runtime\ exists, otherwise any installed Python 3.9+.
Set sh = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
dir = fs.GetParentFolderName(WScript.ScriptFullName)
py = dir & "\runtime\python\pythonw.exe"
If Not fs.FileExists(py) Then py = "pyw"
sh.CurrentDirectory = dir & "\app"
sh.Run """" & py & """ """ & dir & "\app\server.py""", 0, False
