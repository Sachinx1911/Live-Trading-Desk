# Video: "I Gave JARVIS Full Control of My Computer" (Zubair Trabzada, AI Workshop)

- https://youtu.be/ud7wzdiM0gk · 16 min 50 s · published 2026-08-18
- Studied from the transcript the owner supplied (2026-11-21); frames not reviewed (ads played).
- Built with Claude Code by the author; sold as a prompt pack (free) and a ready-made zip (paid
  community). No public repo; everything below is his claim, shown working in the demo.

## What the assistant does

| Capability | How it behaves |
|---|---|
| **Pointer** | Owner shares a screen and asks "where is the button to create a reel?"; JARVIS draws an **arrow** on the right control and says what to click |
| **Screen takeover with narration** | "Take over my screen and create an ads campaign": it clicks, types and scrolls step by step in Meta Ads Manager and **narrates every step aloud** ("Clicking create… naming the campaign… budget defaults to $20, leaving it…") |
| **Interrupt and hand back** | Owner says "stop, I'll take over"; it stops at once ("Already at the wheel, sir") and returns control |
| **Drafts only, stops before money** | It builds everything as a **draft** and never presses Publish: "I stop at the button that spends your money… the last click is a human's job" |
| **Sees only while shared** | When screen sharing stops, the assistant disappears and can no longer see anything |
| **Second brain** | All business notes and files live locally in an organised folder/graph; "pull up the free school community funnel" retrieves the linked notes. New work (e.g. the ad campaign) is added as a note for later questions ("how much did we spend?") |
| **Tools** | Gmail, Google Calendar, Drive/Docs/Sheets, a leads table; creates an invoice from a lead's record and saves it to Drive, emails a payment reminder |
| **Channels** | Desktop app; **Telegram** from outside (text, or "voice on" for a voice-note reply); **phone number** (Twilio + Retell AI) to call restaurants/businesses and to be called |
| **Phone security** | A caller must give a **PIN** before it shares anything; otherwise it hangs up |
| **Persona** | Always listening, adds dry comments ("an assistant with autonomous access to your card is called a co-founder") |

## What we can take

| Idea | For us |
|---|---|
| Narrate every step while acting | FRIDAY/JARVIS narration in the panel (and by voice in Mark 2) whenever a Yellow plan runs: the owner always knows what is happening |
| "Stop" works instantly and hands control back | Our "stop / undo that" rule (plan §2.3) as a first-class, always-available command, including mid-plan |
| **Stop at the money button** | Exactly our Red rule. His version is a habit of the prompt; ours is enforced server-side (tool runner + execution gateway), never by the prompt |
| Draft-first for everything | Our drafts: strategy versions, rule drafts, plan proposals |
| Pointer arrow "show me where" | A KAREN/teaching tool: highlight the control in our own UI ("where do I see PCR?") without acting. Cheap because we own the UI: no screen vision needed, just a highlight command to the panel |
| Sees nothing unless shared | Vision only on explicit command (already noted for the computer-vision video) |
| Second brain + saving outcomes as notes | Matches our `jarvis_notes` with provenance (research note §4); his notes include figures, ours store ids and fetch numbers |
| Telegram as the away channel, voice notes | Our Telegram notifier becomes a JARVIS channel (Green questions and reports from outside); anything Yellow/Red from Telegram still asks for confirmation |
| PIN before answering on a remote channel | Remote channels (Telegram, phone) need a second factor before revealing positions or P&L; ties in with TOTP in Phase 10 |

## What to avoid / differences

- **Controlling third-party UIs by clicking** (Meta Ads) is fragile and, for brokers, forbidden for us:
  orders go only through the deterministic gateway API, never by driving a broker website.
- Safety by prompt ("he won't publish") is not enough for money; enforcement must be in code.
- Always-listening microphone: privacy and cost; ours stays push-to-talk or wake-word, Mark 2.
- Selling point is a packaged product; no code to check, so treat every capability as a claim.

## Verdict

The most complete picture so far of the **experience** the owner wants: narrated actions, instant
stop, draft-first, stop before money, second brain, Telegram and phone as remote channels. Almost
every safety idea already exists in our plan; the useful additions are **narration**, the
**pointer/highlight teaching tool**, and **PIN on remote channels**.
