# Memory Band: 2-minute pitch

Two speakers: **A** talks to the judges, **B** wears the bracelet and plays Margaret.
Before you start: bracelet charged and connected (solid blue), live page open on the laptop,
phone with the Memory Band app and ntfy on screen, **Start demo** pressed 1 minute before.

---

## 0:00 – 0:25 · The problem (A)

> "Did I lock the door? Did I take my pill? Where did I leave my glasses?
> For millions of older adults, memory loss turns everyday life into constant worry.
> Phones don't help. They mean looking and typing, and remembering to do it.
> So families end up being the memory, answering the same questions again and again."

## 0:25 – 0:45 · The idea (A)

> "But people talk through what they do: 'okay, locking up', 'there, pills done'.
> Memory Band listens to that through the Vexo bracelet, and becomes a memory that
> needs zero effort. You just talk. It speaks up on your phone at the right moment,
> before something goes wrong."

## 0:45 – 1:35 · Live demo (B speaks, A narrates)

| B says to the bracelet | A says while the phone buzzes |
|---|---|
| "Can we get the check?" | "Margaret is finishing lunch. Before she even stands up, her phone says: *do you have your phone, wallet and glasses?*" |
| "Taking my blood pressure pill." | "She takes her pill. Memory Band notes the time and her exact words." |
| "Time for my pill." | "A bit later she forgets she already took it. *Wait, you already took it at 2:10.* That's a double dose avoided, and her family is quietly told." |
| "Okay, locking up." … "Did I lock the door?" | "And when the doubt comes back, she just asks. The answer has the time and what she said." |

> Point at the laptop: "Everything she says, what it understood, and every alert, live."
> Show the phone app's **Family** tab: "Her family sees the same, as it happens."

If the pill reminder fires during the demo (2 minutes after Start demo), say:
> "And that one came on its own: her 2 o'clock pill time passed with nothing heard."

## 1:35 – 1:50 · How it works (A)

> "The Vexo bracelet streams Margaret's voice over Bluetooth. Deepgram turns it into
> text as she speaks. Our backend picks out the moments that matter, pills, door,
> leaving a place, and a rules engine decides when to step in. Reminders go to her
> phone as notifications, even when it's locked, and urgent ones to her family."

## 1:50 – 2:00 · Close (A)

> "Next: appointments, promises to family, and recognising who she's talking to.
> Memory Band: she just talks, and it remembers for her."

---

## Rehearsal tips

- **Say the demo lines exactly as written.** Without an OpenAI key, the app only knows
  set phrases. Other wordings may not trigger anything.
- **Keep other talk away from the bracelet.** It reacts to trigger words in any
  conversation ("going out", "the check").
- **Wait for each buzz** before the next line; give it 2–3 seconds.
- **Backup if the bracelet drops:** type the same lines in the box on the live page,
  or tap the grey sentence buttons. The phone gets the same notifications.
- **Only claim what's running:** say "OpenAI" only if the key is in `.env`, and don't
  mention voice or a native app (reminders are phone notifications, and the app is
  added to the home screen from the browser).

## For a judge who asks

- **Privacy?** Speech goes to Deepgram only to be turned into text (with "do not train
  on this" switched on). Transcripts and the timeline stay on our own laptop. The phone
  app needs a private key.
- **What if it mishears?** Every reminder quotes what she actually said, so she can
  judge it herself. A wrong guess costs one notification, not a wrong action.
- **Why not just a pill box or a phone alarm?** Those cover one problem each and need
  setting up. This covers the door, pills, belongings and repeated questions from
  speech she's already saying.
