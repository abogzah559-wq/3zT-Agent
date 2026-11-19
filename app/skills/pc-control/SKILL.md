---
name: pc-control
description: Control the Windows PC with mouse and keyboard - open apps, click buttons, fill forms, navigate settings or any program UI, check what is on screen. Arabic triggers - افتح البرنامج، اضغط، تحكم، شاشتي، وش في الشاشة، سو لي في البرنامج.
---
# PC control loop

1. Prefer non-visual ways first: `open` (apps, files, links), `run_command` (PowerShell), keyboard shortcuts. They are faster and more reliable than clicking.
2. Visual loop when needed:
   a. `screenshot` (coordinates are in that image's pixels).
   b. Find the target precisely; click the CENTER of the button/field.
   c. Every control tool returns a new screenshot - check the action worked before the next one.
   d. If nothing changed, try once more (maybe a double click or `focus_window` first), then change approach.
3. Typing: click the field first, then `type_text`. Use `press_keys` for enter, tab, ctrl+a, ctrl+c/ctrl+v, alt+tab, win+r.
4. Bring a window forward with `focus_window` (part of its title) - use `list_windows` to see titles.
5. Never click "Delete", "Format", "Uninstall" or payment buttons unless the user explicitly asked.
6. Useful shortcuts: win+r (Run), win+e (Explorer), ctrl+shift+esc (Task Manager), win+i (Settings), alt+f4 (close window), win+d (desktop).
