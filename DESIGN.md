# Design

Ease uses a restrained mint light, generous black space, and Inter typography provided by Raven. The work screen lives toward the right of the display. A single primary action starts a break, and small secondary controls manage timing.

The break has four stages.

1. Four fixed light targets invite a gentle change in gaze. Each advances after a 5 seconds of accumulated valid gaze within a 55-pixel radius. A natural blink pauses the hold. Looking at another location resets it. The points are close enough to avoid deliberately demanding extreme eye movement.
2. A 20-second distance phase asks the wearer to look at a real object across the room. The painted instructions dim after three seconds. A timed transition avoids requiring the wearer to look back to acknowledge completion.
3. An optional eye-rest stage estimates ten seconds of closure from recovered tracking loss. A chime prompts reopening. The user can skip the stage. The interface explicitly labels the result as estimated.
4. A brief completion screen returns automatically to the configured work interval.

The pause control is always available during a break. Skip returns to work immediately. Reminders wait for consent to begin, and a five-minute snooze offers an easy way to finish the current thought.

The model uses elapsed monotonic time. A suspended computer can cause a reminder to become due, but a long processing gap cannot count as a completed gaze hold. Missing sensor data pauses a hold. Invalid coordinates and interrupted sampling cannot count as valid observations. No gaze samples are saved or transmitted. Only the selected reminder interval is stored with the operating system's local application settings.

## Media direction

The 68-second narrated video is recorded through the official Raven simulator's Record control. It shows the simulator's real rendered view directly, without added titles, lower captions, or decorative frames. It includes the reminder, four gaze targets, the full distance interval, estimated closed-eye rest, and completion. Screenshots are extracted from that recording. Scripted gaze drives the demo inside the actual running app. Cartesia English narration is added without altering the recorded video stream.
