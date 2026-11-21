# UI research: Lumen Bank / Company Brain

Goal: make every screen feel like a calm, professional banking product (dark mode, Stripe/Mercury-level polish) for bank staff (relationship manager, IT, compliance).
Sources: Mobbin (web, plus a few iOS screens for approval patterns). I looked at every screenshot. Metadata alone wasn't enough.

## Reference screens and what we take from each

| # | Screen | Pattern we take |
|---|--------|-----------------|
| 1 | [Mercury: home, dark mode](https://mobbin.com/screens/8fd5635e-a61d-4d11-b4c9-c1963ddd0da1?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp) | Near-black neutral canvas (not blue-tinted), 1px hairline borders, cards with a small header plus a "View all" link, and a greeting as the page title. This sets the base of the visual language. |
| 2 | [Mercury: home, empty state](https://mobbin.com/screens/d0553915-6c36-4702-a8ef-907d38c5099e?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp) | Plain-English status lines ("You don't have any tasks requiring your action") and empty states centred in the container where the data would be, with one sentence of explanation. Used for every empty list (approvals, memory, outbox, security). |
| 3 | [Revolut Business: approval panel](https://mobbin.com/screens/82df1cb8-945f-4649-ad95-3717f0f7e784?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp) | Approve and Reject sit next to each other with icons (✓ / ✕), and Approve has the stronger style. Status is shown as a text pill. Used for every Approve/Reject pair. |
| 4 | [Deel: action required](https://mobbin.com/screens/b6d82ee0-8694-4f55-a1d5-9f0964c8b13c?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp) | A bulk "Approve all your pending (N)" action at page level, with per-row approve and reject. This became our single primary button "Approve all routine reminders (N)". |
| 5 | [Workable: inbox with inline approvals](https://mobbin.com/screens/206a61d4-bf58-4bca-b9b6-8226d88ffc66?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp) | Inbox rows: icon, title, one-line reason, meta line, and the actions on the right. The details expand inline instead of opening a new page. Used for "Preview message" in Approvals. |
| 6 | [Airwallex: spend request side panel](https://mobbin.com/screens/89c96631-be20-4176-be78-d24175e013ed?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp) | "Pending your approval" status chip, plus key facts (amount, requester, category) laid out as label/value pairs before the decision. This shaped how our meta line shows amount, days late and who proposed the action. |
| 7 | [Dropbox Dash: AI answer with sources](https://mobbin.com/screens/fc54be30-29ff-430c-9554-7858c47373e8?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp) | Prose answer with small inline citation chips, a "1 source" row under the answer, a large rounded composer pinned to the bottom, and suggested follow-ups as cards. This is the main model for **Ask**. |
| 8 | [Customer.io agent: references list](https://mobbin.com/screens/fafcbfb9-fa85-4b4d-b17f-54df962305b5?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp) | Numbered references with titles, readable without opening the source. We render sources as numbered chips (`1 Credit Policy v3`) that match the inline `[1]` markers. |
| 9 | [Jobber: "Good evening, Sam" + workflow strip](https://mobbin.com/screens/26563ea4-1b26-4a35-8c59-f9e8aab7de5c?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp) | A greeting, then a joined KPI strip (one card divided into cells), then a "To do" list. This is exactly the structure of **Today**: KPIs that link to the work, then the brief. |
| 10 | [Stripe Workbench: dark overview](https://mobbin.com/screens/a14144e6-2127-44f1-b498-50124a1e114c?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp) | Stripe's dark-mode density: 12-13px muted labels, large numerals, and a dashed or quiet empty container ("No deliveries in the last 7 days"). Used for the Security scoreboard before any red-team report exists. |
| 11 | [Vanta: event log](https://mobbin.com/screens/41659ab7-5710-4abf-91ca-c6bf482c9b0b?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp) and [Cloudflare: audit logs](https://mobbin.com/screens/fa5520ff-fda8-435f-b65b-bf910991fab4?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp) | Audit table: date on top with the time underneath in muted text, actor with their role underneath, the action as a short label, and "Details" disclosed on demand. Used for **Audit trail** and **Security**. |
| 12 | [Revolut Business iOS: review transfer](https://mobbin.com/screens/c63b0b45-46b5-4f5e-8661-a65051c19eeb?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp) | On dark grouped surfaces, the review shows only label/value pairs and one primary button. This reinforced "one primary action per area". |

### The 3 best
1. [Mercury: home, dark mode](https://mobbin.com/screens/8fd5635e-a61d-4d11-b4c9-c1963ddd0da1?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp): the overall visual language.
2. [Revolut Business: approval panel](https://mobbin.com/screens/82df1cb8-945f-4649-ad95-3717f0f7e784?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp): approval ergonomics.
3. [Dropbox Dash: AI answer with sources](https://mobbin.com/screens/fc54be30-29ff-430c-9554-7858c47373e8?utm_source=claude-code&utm_medium=ai-assistant&utm_source_platform=mcp): what a trustworthy AI answer looks like.

## Design system decisions (implemented in `app/ui.py`)

**Colour (dark only).** All tokens live on `:root`.

| Token | Value | Use | Contrast |
|---|---|---|---|
| `--bg` | `#0b0c0e` | canvas | n/a |
| `--surface` / `--surface2` | `#141518` / `#1a1c20` | cards, raised controls | n/a |
| `--line` / `--line2` | `#25272d` / `#30333a` | hairlines, control borders | n/a |
| `--ink` | `#ececef` | primary text | ≈ 16:1 on surface (AAA) |
| `--ink2` | `#b4b8c1` | body/secondary text | ≈ 9:1 (AAA) |
| `--mute` | `#868b96` | labels, meta | ≈ 5.2:1 on surface (AA) |
| `--faint` | `#5f646e` | separators and placeholders only, never information | n/a |
| `--accent` | `#5e6ad2` | the primary button (white text ≈ 4.6:1, AA) and the count badge | |
| `--accent-ink` | `#a9b1ff` | links | ≈ 8:1 |
| `--ok` / `--warn` / `--bad` / `--info` | `#4cc38a` / `#e8a952` / `#f2727f` / `#7aa2ff` | status text and icons, all ≥ 6:1 on surface; tint backgrounds at 12% alpha | |

**Status colours** are used only for meaning: green means approved/executed/safe, amber means needs a human (exceptions, pending, abstain, re-identification), red means rejected/blocked/denied, and indigo means waiting for you. Pills always pair the colour with a dot and a text label, so colour is never the only signal.

**Type.** Inter / system UI stack. The scale is 12 (meta), 13 (labels, buttons), 14 (body), 16 (section titles), 20 and 28 (page titles, −0.6px tracking). Numbers use `tabular-nums`, so amounts line up in tables and KPIs.

**Spacing and density.** The spacing scale is 4, 8, 12, 16, 20, 24, 32, 48 px. Table rows are about 44px and inbox rows have 16px vertical padding. Content is capped at a max width of 1040px (1180px for the audit table) so lines stay readable.

**Shape.** Cards use a 10px radius, buttons 7px and chips 5-6px. Elevation is a hairline border plus a 1px inner highlight. There are no glows or gradients except the avatar.

**Hierarchy rules.**
- Each page has one header: title, a one-sentence plain-English explanation, and at most one primary action on the right.
- In row actions, Approve is a bordered button with a green ✓ and Reject is a quiet ✕. The filled indigo button is kept for the page-level action (for example "Approve all routine reminders").
- Lists are a single panel with row dividers (Linear/Mercury inbox style), not a stack of floating cards.
- Tables use muted 12px headers, right-aligned amounts, and two-line cells (main value + muted secondary).

**Privacy marks.** Re-identified names (authorised roles only) get a subtle amber dotted underline with a tooltip ("re-identified for your role"). Pseudonyms render as a monospace chip, for example `<CLIENT_12>`. The Security page always shows pseudonymised text, whatever the viewer's role.

**Iconography.** One 24px-grid stroke set at 1.75 stroke weight (lucide-style), drawn at 16px. Icons sit in 32px tiles tinted by tone.

**Empty states.** Every list has one: an icon tile, a one-line title, one sentence of explanation, and an action when there is a next step. Examples: "You're all caught up", "Nothing has left the bank", "No red-team run yet".

**Motion.** 120ms colour and background transitions only, plus a three-dot typing indicator in Ask. All motion is off under `prefers-reduced-motion`.

**Responsive.** At 1180px and below the sidebar narrows to 212px. At 960px and below it collapses to a 64px icon rail, suggestion cards stack, and row actions wrap under their row.
