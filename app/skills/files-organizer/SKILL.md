---
name: files-organizer
description: Organize, find, rename, sort, clean up or back up files and folders; find duplicates and large files; batch rename; sort downloads by type/date. Arabic triggers - رتب، نظم، ملفات مكررة، أكبر الملفات، إعادة تسمية، نسخة احتياطية، فرز.
---
# Files organizer

1. Look first: `list_dir` / `search_files` to understand what exists. Report counts and sizes before acting.
2. For big plans (moving many files) show the plan as a short table (from → to) and then do it; moves ask the user automatically.
3. Batch work is best done in ONE `run_command` PowerShell script, e.g. sort Downloads by extension:
   ```powershell
   $src="$HOME\Downloads"; Get-ChildItem $src -File | ForEach-Object {
     $d = Join-Path $src ($_.Extension.TrimStart('.').ToUpper());
     New-Item -ItemType Directory -Force $d | Out-Null; Move-Item $_.FullName $d }
   ```
4. Largest files: `Get-ChildItem C:\Users\$env:USERNAME -Recurse -File -ErrorAction SilentlyContinue | Sort Length -Desc | Select -First 30 FullName,@{n='MB';e={[int]($_.Length/1MB)}}`
5. Duplicates: `find_duplicates` (read-only + CSV report). Never delete duplicates without listing them and getting approval; deletion goes to the Recycle Bin.
6. Batch rename example: `Get-ChildItem *.jpg | % -Begin {$i=1} { Rename-Item $_ ("photo_{0:D3}.jpg" -f $i++) }`
