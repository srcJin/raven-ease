# Raven Minihack submission

**Project:** Ease

**One-line pitch:** A quiet companion that invites a gentle gaze break, then gives your eyes 20 seconds with the world beyond the display.

**Repository:** https://github.com/srcJin/raven-ease

**Demo:** [English narrated simulator walkthrough](media/demo.mp4)

**Screenshots:** [Focus](media/01-focus.png), [Reminder](media/02-reminder.png), [Gaze](media/03-gaze.png), [Distance](media/04-distance.png), [Complete](media/05-complete.png), [Eye rest](media/06-eye-rest.png)

**Built for Raven:** Python, RavenApp, RunApp, gaze-friendly Raven Buttons, EyeControl on device, and a custom Qt-painted interface.

**What works:** Local reminder scheduling, configurable intervals, pause, snooze, skip, four-point gaze progression with five seconds per point, natural-blink tolerance, the 20-second real-world distance phase, estimated closed-eye rest with recovery checks and an audio chime, completion, and reproducible media capture.

**Validation:** Automated state checks and desktop rendering. The submitted video is a simulator demonstration with scripted gaze. Hardware testing remains pending. Gaze loss estimates closure and cannot verify eyelid state. The exact exercise timing is a design choice. See [research notes](RESEARCH.md).

**Submission destination:** parth@raven.computer
