Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
curDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = curDir

pyPath = "pythonw.exe"
If fso.FileExists("C:\Python313\pythonw.exe") Then
    pyPath = "C:\Python313\pythonw.exe"
ElseIf fso.FileExists("C:\ProgramData\Anaconda3\pythonw.exe") Then
    pyPath = "C:\ProgramData\Anaconda3\pythonw.exe"
End If

WshShell.Run """" & pyPath & """ """ & curDir & "\main.py""", 0, False
Set WshShell = Nothing
Set fso = Nothing
