' Starts the home page silently (no black window). With the word open after it, also opens the page.
Set sh = CreateObject("WScript.Shell")
here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = here
sh.Run "cmd /c """ & here & "\server.bat""", 0, False
If WScript.Arguments.Count > 0 Then
  WScript.Sleep 3000
  sh.Run "http://127.0.0.1:5000"
End If
