Option Explicit
Dim shell, fso, baseDir, batFile
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
batFile = fso.BuildPath(baseDir, "Iniciar_TechNord.bat")

shell.CurrentDirectory = baseDir
shell.Run Chr(34) & batFile & Chr(34), 0, False
