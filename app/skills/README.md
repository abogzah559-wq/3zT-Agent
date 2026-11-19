# Skills

Each folder is a skill: a `SKILL.md` (YAML front matter with `name` and `description`, then instructions) plus optional scripts and references. The agent sees only the names and descriptions, and loads a full skill with `load_skill` when a task needs it.

- Custom skills: ai-generation, video-editing, video-repair, image-editing, subtitles-voice, web-research, pc-control, files-organizer, windows-admin.
- From [anthropics/skills](https://github.com/anthropics/skills) (Apache License 2.0, see each folder's LICENSE.txt and THIRD_PARTY_NOTICES.md): pdf, xlsx, docx, pptx, slack-gif-creator, webapp-testing, frontend-design, algorithmic-art, skill-creator.
- Install more from any GitHub folder that contains a SKILL.md: Settings → Skills, or ask the agent ("install this skill: <link>"). Installed skills live in `%APPDATA%\3zT-Agent\skills`.
