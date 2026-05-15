# NEXUS Remotion Video Series — Executable Plan

**Author:** V>> (planning session, Gen ~512)
**Drafted:** 2026-05-01 (amended from single-video to series)
**Future session:** runs `Skill(skill="remotion-video-creation")` against this brief
**Working directory for future session:** `~/nexus-poc` (discovery + brand) +
`~/CodeTonight/grip-remotion-demo` (Remotion runtime)
**First deliverable:** `nexus-time-entries.mp4` (45s @ 1920×1080, h264, silent)
**Series target:** 9 feature teasers, one per NEXUS differentiator

---

## 1. Recommended scope — Series of feature teasers

**Decision:** Render scope = **SINGLE FEATURE SHOWCASE × 9**, all sharing one
template. First teaser = **voice-first time entries** (this plan focuses there).
The remaining 8 follow the same template (§11) and reuse the brand-token
module + scene primitives.

**Rationale for series-not-omnibus:**
- A 60s omnibus compresses 9 differentiators into 3 acts — every cut is lossy
  and no single feature gets to breathe. Each feature deserves its own arc.
- Each teaser is independently shareable. Craig can drop the time-entries
  teaser into a sales email about billing efficiency, the routing teaser into
  a compliance conversation, the audit-chain teaser into a governance talk —
  without sending one monolithic video that's 80% irrelevant to that prospect.
- Series production amortises overhead. Brand tokens, animation rules,
  composition shell, custom-scene library are built once for teaser #1; each
  subsequent teaser reuses them and only swaps the middle act.
- A series builds momentum on social channels — one teaser per week sustains
  presence without burning content all at once.
- Per-teaser duration (30–45s) hits the LinkedIn-feed engagement sweet spot
  better than 60s+.

**Lead teaser: voice-first time entries.** Reasoning:
- It's the *most universally relatable* differentiator. Every billing lawyer
  loses time to time-tracking. The pain is immediate.
- The user flow is short and demo-ready (~10 seconds: dictate → entry appears).
  Other teasers (multi-intent drafting, FADP routing) have more setup overhead.
- Real implementation already shipped: `frontend/src/app/(main)/time/page.tsx`,
  backend `routes.py:832-843` (parse → store → audit), v0.2.0 changelog
  voice-transcript-persistence entry.
- It demonstrates the *full stack* in 45 seconds: STT (Groq Whisper) → LLM
  parsing (Claude Haiku) → structured persistence (SQLite TimeEntry) →
  audit chain (HMAC-SHA256). One teaser shows the architecture.

**Conditional override AskUser at session start:**

```
Question: "Pre-locked: voice-first time entries teaser (45s, landscape, Single
Feature Showcase). First in a 9-video series. Override?"
Options:
  - Keep recommended (voice-first time entries, 45s, 1920×1080)
  - Different first teaser (operator names which feature: drafting / routing
    / audit-chain / search / graph / SOPs / SharePoint / matter-scoping)
  - Different format (portrait 1080×1920 for LinkedIn, square 1080×1080)
  - Different duration (30s short / 60s extended)
```

If kept, proceed straight to Phase 6 (implementation) — Phase 3 questions
collapse to confirmations.

---

## 1.5. Series template (invariant across all 9 teasers)

This template is the contract every teaser in the series adheres to. Future
teaser sessions only specify the *middle act* and the *headline copy* — every
other element is fixed.

### Duration & format
- 45 seconds (1350 frames @ 30fps) — default
- 30s short variant available for social-cut renders
- 1920×1080 landscape primary; 1080×1920 portrait secondary (for LinkedIn)
- Square 1080×1080 only on operator request (Instagram-specific)

### 3-act rhythm (frames are at 30fps)
| Act | Frames | Time | Purpose |
|---|---|---|---|
| Hook | 0–240 | 0–8s | Pain statement + product anchor (NarrationOverlay) |
| Feature demo | 240–1110 | 8–37s | The single feature, animated end-to-end |
| CTA | 1110–1350 | 37–45s | "ChiefOfStaff.pro — voice in, result out" + URL |

### Brand identity (every teaser)
- Swiss Nihilism palette via `nexus-tokens.ts` (§5)
- Square corners universal (`borderRadius: 0`)
- System sans for UI / `ui-monospace` for code/transcript
- British English copy
- CHF currency on any pricing surface
- Tagline "voice in, result out" appears verbatim at CTA

### Hook structure (invariant copy template)
```
Line 1 (frames 12–60, fade-in): "[Pain statement, ≤8 words]"
Line 2 (frames 60–120, fade-in): "[Reframe as ChiefOfStaff feature, ≤12 words]"
Line 3 (frames 120–180, optional small-caps subtitle): "ChiefOfStaff.pro"
Animate out (frames 180–240).
```

Examples per teaser:
- Time entries: *"Lawyers lose 6% of billable hours *recording* billable hours."* / *"What if you could just say it?"*
- Drafting: *"Two documents. One dictation."* / *"Drafting at the speed of voice."*
- Routing: *"Confidential. Caution. Public."* / *"The model decides where each query lives."*
- Audit chain: *"Every AI decision. Tamper-evident. Falsifiable."*
- Search: *"Search English. Search German. Search meaning."*
- Graph: *"112 entities. 125 relationships. Five documents."*
- SOPs: *"No conflict check, no procedure."*
- SharePoint: *"Where your documents already live."*
- Matter scoping: *"Client A. Or Client B. Never both."*

### CTA (invariant)
- Frame 1110–1170: "ChiefOfStaff.pro" — large, ink-dark, animate in
- Frame 1170–1230: "voice in, result out" — accent orange small-caps subtitle
- Frame 1230–1290: `chiefofstaff.pro` — URL in mono at base
- Frame 1290–1350: orange rule animates across width, fade out

### Reusable scene primitives (built once, shared across teasers)
- `NarrationOverlay` (existing) — re-themed via `nexus-tokens.ts`
- `VoiceWaveformDemo` (NEW, built for teaser #1, reused for teasers #2)
- `TimeEntryCard` (NEW, teaser #1) — generalises to `EntityCard` for #2
- `BillableSummary` (NEW, teaser #1) — generalises to `MetricSummary` for others
- `TerminalReplay` (existing) — used in teasers #3, #4 (routing, audit)
- `CodeDiff` (existing) — used in teaser #4 (audit-chain implementation)
- `PRCard` (existing) — used only if a teaser leans into release evidence

### Animation rules (invariant, PARAMOUNT)
- Every element animates IN over ≥12 frames AND OUT over ≥12 frames
- No hard cuts — fade or spring transitions only
- Spring physics for entrance (stiffness 120, damping 18)
- Linear/easeInOut interpolation for sustained motion
- No element static for >3 seconds without micro-animation (subtle pulse, scale)

### Out of scope for series v1
- Real audio narration (Remotion render is silent)
- Music or SFX
- DE multilingual subtitle tracks (defer to series v2)
- Burned-in captions (defer to series v2)

---

## 2. Teaser #1 — Voice-First Time Entries (45s detailed outline)

**Composition id:** `NexusTimeEntriesDemo`
**Duration:** 1350 frames (45s @ 30fps)
**Output file:** `nexus-time-entries.mp4`

### Act 1 — Hook (0–8s, frames 0–240)
Scene: `NarrationOverlay` (re-themed)
- Frames 12–60: *"Lawyers lose 6% of billable hours…"* fades in (ink-dark on paper-grey)
- Frames 60–120: *"…recording billable hours."* fades in below
- Frames 120–180: subtle pulse on the 6% (scale 1.0 → 1.04 → 1.0)
- Frames 180–240: text fades out, paper-grey holds

> Note on the 6% claim: this is an *industry observation* not a NEXUS measurement.
> If V>> wants strict source-traceability, swap to: *"Time entry. Manually. Every hour. Every day."* — a true descriptive statement instead of a sourced statistic.

### Act 2 — Feature demo (8–37s, frames 240–1110)

#### Sub-act 2A — Voice capture (frames 240–540, 8–18s)
Scene: `VoiceWaveformDemo`
- Frames 240–280: microphone glyph (Lucide `Mic`) springs in centred, ink-dark
- Frames 280–320: 32-bar waveform animates beneath (visual only, driven by `useCurrentFrame() % 60`)
- Frames 320–540: transcript types out below the waveform at 2 chars/frame:
  > *"Spent forty-five minutes drafting an NDA for Acme AG."*
- Frame 540: transcript fully rendered, waveform pulses one final time

#### Sub-act 2B — AI parsing (frames 540–720, 18–24s)
Scene: bridging animation (no new scene needed — happens inside `VoiceWaveformDemo`)
- Frames 540–600: small "Claude Haiku" badge animates in below transcript (mono text, accent orange border)
- Frames 600–660: parsing arrows animate from transcript words to structured fields:
  - "forty-five minutes" → `duration_minutes: 45`
  - "drafting an NDA" → `description: "Drafting NDA"`
  - "Acme AG" → `matter: "Acme AG"`
- Frames 660–720: arrows fade out, structured fields hold

#### Sub-act 2C — Entry materialises (frames 720–960, 24–32s)
Scene: `TimeEntryCard` (NEW)
- Frames 720–780: card containing the parsed entry springs in from below the
  waveform, replacing it. Card has square corners, white surface, ink-grey border.
- Card layout (matching `time/page.tsx` real shape):
  ```
  ┌──────────────────────────────────────────┐
  │ Acme AG                       2026-05-01 │
  │ Drafting NDA                             │
  │ ──────────────────────────────────────── │
  │ 45 min        500 CHF        Billable ●  │
  └──────────────────────────────────────────┘
  ```
- Frames 780–840: each field animates in with 18-frame stagger (matter, then
  description, then duration, then CHF value, then billable indicator)
- Frames 840–900: a tiny "audit-chained" mark (Lucide `Link`) appears at the
  card's top-right with the first 8 chars of an HMAC-SHA256 hash in mono,
  ink-faded (accent orange on hover, but no hover in video — static accent)
- Frames 900–960: card holds, gentle 2-pixel scale pulse to maintain motion

#### Sub-act 2D — Daily summary update (frames 960–1110, 32–37s)
Scene: `BillableSummary` (NEW)
- Frames 960–1020: a small summary panel slides in from stage right beside the card
- Panel shows: "Today: 6.5 hr / 4,200 CHF / 9 entries" — number rolls up with `interpolate`
- Frames 1020–1080: numbers tick from previous values to new (animated counter):
  - 6.5 hr → 7.25 hr (45 min added)
  - 4,200 CHF → 4,700 CHF (500 CHF added)
  - 9 entries → 10 entries
- Frames 1080–1110: summary holds, card + summary both visible

### Act 3 — CTA (37–45s, frames 1110–1350)
Scene: `NarrationOverlay` (re-themed)
- Frames 1110–1170: card + summary fade out
- Frames 1170–1230: *"ChiefOfStaff.pro"* fades in centred, large
- Frames 1230–1290: *"voice in, result out"* in accent-orange small-caps below
- Frames 1290–1320: `chiefofstaff.pro` URL in mono at base
- Frames 1320–1350: orange rule animates across width (left to right via `strokeDashoffset`), then everything fades

---

## 3. Custom Scenes for Teaser #1 (3 new components)

These extend the existing 4 scenes and become the foundation for the series.

### 3.1 `VoiceWaveformDemo.tsx` (REUSED in teasers #2)
Specified in earlier plan. Adds for this teaser: small "Claude Haiku" badge
prop + parsing-arrow overlay (frames 540–720 in §2).

```tsx
interface VoiceWaveformDemoProps {
  transcript: string;
  llmBadge?: string;            // "Claude Haiku" — shown after transcript completes
  parseArrows?: Array<{
    fromWord: string;            // "forty-five minutes"
    toField: string;             // "duration_minutes: 45"
    fromFrame: number;
  }>;
  caption?: string;
}
```

### 3.2 `TimeEntryCard.tsx` (NEW — generalises to `EntityCard` for series)
Renders a structured time entry. The shape matches `TimeEntry` interface in
`time/page.tsx:6-15` exactly — so what's animated is what the actual product
displays.

```tsx
interface TimeEntryCardProps {
  matter: string | null;
  description: string;
  duration_minutes: number;
  value_chf: number;
  billable: boolean;
  timestamp: string;             // ISO
  audit_hash?: string;            // First 8 chars of HMAC-SHA256
  staggerStartFrame?: number;     // For sequenced entrance
}
```

**Token spec:**
- Card surface: `var(--nx-surface)` (#FFFFFF)
- Border: `1px solid var(--nx-rule)` (#d1d5db), square corners
- Matter label: `var(--nx-ink)` (#1a1a1a), system sans, medium weight
- Description: `var(--nx-ink-2)` (#374151), system sans, regular weight
- Duration + CHF: `var(--nx-ink)` for value, `var(--nx-ink-3)` for unit label
- Billable indicator: `var(--nx-good)` dot when true
- Audit hash: mono, `var(--nx-ink-3)`, accent on the link icon
- Date: mono, `var(--nx-ink-3)`, top-right of card

**Animation:** spring entrance from y=+40 with stiffness=120 / damping=18.
Each field stagger-fades in at +18-frame increments after card body lands.

### 3.3 `BillableSummary.tsx` (NEW — generalises to `MetricSummary`)
Three-stat panel with animated counters.

```tsx
interface BillableSummaryProps {
  hours: { from: number; to: number };
  chf: { from: number; to: number };
  entries: { from: number; to: number };
  startFrame: number;             // Frame to begin tick animation
  durationFrames?: number;        // Default 60 (2s)
}
```

**Token spec:** same surface/border as TimeEntryCard. Numbers in `var(--nx-ink)`,
labels in `var(--nx-ink-3)`, accent rule under the heading.

**Animation:** numbers interpolate from `from` → `to` over `durationFrames`
using `interpolate(frame, [start, start+dur], [from, to])`. CHF formatted with
en-GB locale, hours formatted to 2dp. Highlight pulse (scale 1.0 → 1.05 → 1.0)
when each number reaches its final value.

### Scenes deferred to later teasers in the series
| Scene | First teaser using it |
|---|---|
| `RoutingDecisionTree.tsx` | Teaser #3 (FADP sensitivity routing) |
| `IDRChain.tsx` | Teaser #4 (audit chain + Popper falsification) |
| `EntityGraphMini.tsx` | Teaser #6 (interactive entity graph) |
| `SOPGateChain.tsx` | Teaser #7 (SOP gated workflows) |
| `MatterScopeFork.tsx` | Teaser #9 (matter scoping) |

---

## 4. Asset Checklist (Teaser #1)

### Already exists
- ✅ Swiss Nihilism token map — `~/nexus-poc/frontend/src/app/globals.css:7-79`
- ✅ 4 reusable Remotion scenes — `~/CodeTonight/grip-remotion-demo/src/scenes/`
- ✅ Real `TimeEntry` shape — `frontend/src/app/(main)/time/page.tsx:6-15`
- ✅ Real backend pipeline anchor — `backend/app/routes.py:832-843` (parse → store → audit)
- ✅ CHANGELOG anchors (v0.2.0 voice transcript persistence, v0.1.0 voice time capture)
- ✅ Tagline "voice in, result out" — `~/nexus-poc/CLAUDE.md:6`

### Must be built (this teaser)
- 🔨 `nexus-tokens.ts` — design-token module (foundation for entire series)
- 🔨 `VoiceWaveformDemo.tsx` (extended with parse-arrow overlay)
- 🔨 `TimeEntryCard.tsx`
- 🔨 `BillableSummary.tsx`
- 🔨 `NexusTimeEntriesDemo.tsx` — top-level composition
- 🔨 Update `Root.tsx` to register `NexusTimeEntriesDemo`

### Out of scope for this teaser (but built for the series)
- ❌ Real audio narration
- ❌ Music or SFX
- ❌ DE subtitles
- ❌ The 5 deferred custom scenes (they ship with their respective teasers)

### Honesty constraint on the 6% pain-statistic
The "6% of billable hours" figure in §2 Act 1 is a commonly cited industry
observation but NEXUS itself has not measured it. Two options for the future
session:
- **Option A:** Use the 6% figure with subtle citation (e.g., "[industry studies]"
  in tiny text). Risks looking like marketing fluff.
- **Option B (recommended):** Replace with descriptive statement that doesn't
  need a source: *"Time entry. Manually. Every hour. Every day."* — three
  short fragments, builds tension via repetition. Higher-quality copy and
  zero source-trace burden.

Future session must pick A or B before render.

---

## 5. Brand-Token Override Map (NEXUS replaces Remotion defaults)

`~/CodeTonight/grip-remotion-demo/src/nexus-tokens.ts`:

```ts
export const NEXUS_TOKENS = {
  paper: '#EAEAEA',
  surface: '#FFFFFF',
  rule: '#d1d5db',
  rule2: '#e5e7eb',

  ink: '#1a1a1a',
  ink2: '#374151',
  ink3: '#4b5563',
  ink4: '#9ca3af',

  accent: '#ea580c',
  accentInk: '#9a3412',

  good: '#16a34a',
  bad: '#dc2626',
};

export const NEXUS_RADIUS = 0;
export const NEXUS_FONT_UI = 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';
export const NEXUS_FONT_MONO = 'ui-monospace, SFMono-Regular, "SF Mono", Consolas, "Liberation Mono", Menlo, monospace';
```

**Override rule (PARAMOUNT, applies to entire series):** every scene must
import `NEXUS_TOKENS` and reference it instead of literal hex values. Forbidden
literals (grep gates them at §8):
- `#0a0a0a` (Remotion default bg)
- `#1a1a2e` (Remotion default terminal)
- `#f97316` (GRIP orange, not NEXUS orange)
- `#a371f7` (Remotion PR-merged purple)
- `#3fb950` (Remotion PR-open green — use `good` instead)

---

## 6. Phase 3 AskUserQuestion Script (pre-tuned for this teaser + series)

### Q1 — Format
| Option | When to pick |
|---|---|
| **Landscape 1920×1080** ✅ recommended | Web embed, email, sales |
| Portrait 1080×1920 | LinkedIn / mobile-feed primary |
| Square 1080×1080 | Instagram / Twitter |

### Q2 — Duration
| Option | When to pick |
|---|---|
| 30s short cut | Drop daily-summary act, hook + voice + entry only |
| **45s standard** ✅ recommended | Full 3-act with all 4 sub-acts |
| 60s extended | Add bonus beat: detail-modal click-through with editable transcript |

### Q3 — Style
| Option | When to pick |
|---|---|
| **Swiss Nihilism (paper / ink / orange accent)** ✅ recommended | Matches NEXUS brand exactly |
| Documentary (denser captions, more text) | Investor / conference contexts |

### Q4 — Pain-statement source (the §4 honesty issue)
| Option | When to pick |
|---|---|
| **Descriptive — *"Time entry. Manually. Every hour. Every day."*** ✅ recommended | Zero source-trace burden, stronger copy |
| Statistical — *"Lawyers lose 6% of billable hours recording billable hours"* | If V>> can confirm a citable industry source |

Recommended path: Landscape / 45s / Swiss Nihilism / Descriptive pain statement.

---

## 7. Render Commands

```bash
cd ~/CodeTonight/grip-remotion-demo

# Phase 5–6: build token module + custom scenes + composition
# Files touched:
#   - src/nexus-tokens.ts                  [new — series foundation]
#   - src/scenes/VoiceWaveformDemo.tsx     [new]
#   - src/scenes/TimeEntryCard.tsx         [new]
#   - src/scenes/BillableSummary.tsx       [new]
#   - src/NexusTimeEntriesDemo.tsx         [new]
#   - src/Root.tsx                         [edit: register composition]

# Phase 7: preview in Remotion Studio (operator visually verifies)
npm run start
# → http://localhost:3000 → select NexusTimeEntriesDemo → play

# Phase 7: render the MP4
npx remotion render NexusTimeEntriesDemo nexus-time-entries.mp4 \
  --codec=h264 --crf=18

# Phase 8: verify specs
ffprobe -v error -show_format -show_streams nexus-time-entries.mp4
# Expect: duration ≈ 45.000s, 1920×1080, 30fps, h264, no audio
```

**Composition registration in `Root.tsx`:**
```tsx
<Composition
  id="NexusTimeEntriesDemo"
  component={NexusTimeEntriesDemo}
  durationInFrames={1350}
  fps={30}
  width={1920}
  height={1080}
/>
```

---

## 8. Acceptance Criteria

### Mechanical (verifiable by tooling)
- [ ] `npx remotion render` exits 0
- [ ] `ffprobe` confirms: 45.000s ± 0.05s, 1920×1080, 30fps, h264, no audio stream
- [ ] File size between 3 MB and 20 MB (h264/crf=18 sweet spot for 45s)
- [ ] `rg -F '#0a0a0a' src/` returns 0 hits (no GRIP-default backgrounds)
- [ ] `rg -F '#1a1a2e' src/` returns 0 hits (no GRIP-default terminal)
- [ ] `rg -F '#f97316' src/` returns 0 hits (no GRIP orange — NEXUS uses #ea580c)
- [ ] `rg -nF "borderRadius:" src/` only shows `borderRadius: 0` or none
- [ ] TypeScript compiles clean (`npx tsc --noEmit`)
- [ ] `nexus-tokens.ts` is the only place hex literals appear in scene files

### Editorial (V>> review)
- [ ] All copy is British English
- [ ] Tagline "voice in, result out" appears verbatim at CTA
- [ ] CHF used for currency (no $/€)
- [ ] Pain statement matches §6 Q4 chosen option
- [ ] Time entry data uses real `TimeEntry` shape from `time/page.tsx:6-15`
- [ ] HMAC-SHA256 audit-chain mark uses real hash format (8 hex chars), not lorem
- [ ] Transcript text plausible for a Swiss law firm dictating in EN

### Aesthetic (V>> review)
- [ ] Every visual element animates IN and OUT (≥12 frames each direction)
- [ ] No static element for >3s without micro-animation
- [ ] Square corners universal
- [ ] Single orange accent — no purple, no green except billable-good indicator
- [ ] Paper-grey background dominant
- [ ] Typography hierarchy readable at 100% on a 13" screen

### Functional (playback)
- [ ] Plays cleanly in QuickTime, VLC, Chrome `<video>`
- [ ] No frame drops, no scene-boundary flashes
- [ ] Act timing: hook ≤8s, demo middle ≥25s, CTA ≤8s

---

## 9. Rollback / Cleanup

### If render fails
- Custom scenes are isolated — easy to revert to TerminalReplay-only fallback
  variant (~1 hour to ship a much simpler version)
- `nexus-tokens.ts` and the new scenes are leaf modules — safe to delete
  without breaking existing `ChatwootDemo` or `GripCommanderV050Demo`

### If aesthetic doesn't land
- Render a 5-second `NexusTokenSwatch` test composition first — costs ~5min,
  catches token-application bugs before committing to full 45s render

### Cleanup
- `nexus-time-entries.mp4` → keep at project root or move to
  `~/nexus-poc/docs/videos/` (gitignored — videos are large binaries)
- Bundler cache under `.remotion/` is safe to leave; speeds future renders

### After teaser #1 ships
- Commit `nexus-tokens.ts` + the 3 new custom scenes to
  `~/CodeTonight/grip-remotion-demo` so teasers #2–9 can branch off
- Tag the commit `v2.0-nexus-series-foundation` for traceability

---

## 10. Estimated Wall-Clock Time

### Teaser #1 (this plan): 4–5 hours
| Phase | Activity | Wall-clock |
|---|---|---|
| Phase 0 | Scope confirmation (override AskUser) | 2 min |
| Phase 3 | Preferences (4 AskUser, pre-tuned) | 3 min |
| Phase 5 | `nexus-tokens.ts` module | 20 min |
| Phase 6.1 | `VoiceWaveformDemo.tsx` (with parse-arrows) | 75 min |
| Phase 6.2 | `TimeEntryCard.tsx` | 45 min |
| Phase 6.3 | `BillableSummary.tsx` | 45 min |
| Phase 6.4 | `NexusTimeEntriesDemo.tsx` (assembly + sequence timing) | 45 min |
| Phase 6.5 | `Root.tsx` registration + studio preview | 15 min |
| Phase 7 | Render + ffprobe + first review | 20 min |
| Phase 7.5 | Iteration on animation timing / token bugs | 20–40 min |
| Phase 8 | Delivery summary + V>> sign-off | 10 min |

**Critical path:** the three custom scenes (3.1, 3.2, 3.3) are independent
and can be parallelised via `bg-dispatch` Shape A — wall-clock drops to ~2.5h.

### Teasers #2–9: ~1.5–2 hours each
- Brand tokens, animation conventions, composition shell already exist
- Only the middle-act scene(s) need building
- Hook + CTA are template-driven (copy swap only)
- Total series time estimate: 4–5h (#1) + 8 × ~1.75h (#2–9) = ~18–20h
- Rendering one teaser per week sustains for ~9 weeks of social presence

---

## 11. Series Roadmap (the 9 teasers)

| # | Feature | Lead scene | Source anchor |
|---|---|---|---|
| **1** | **Voice-first time entries** ← **THIS** | `TimeEntryCard` | `time/page.tsx`, v0.2.0 |
| 2 | Multi-intent voice drafting | `EntityCard` (NDA + Letter cards) | v0.2.0 changelog |
| 3 | Sensitivity-routed LLM (FADP) | `RoutingDecisionTree` | `routes.py` routing logic, v0.1.0 |
| 4 | HMAC audit chain + IDR + Popper | `IDRChain` | audit chain code, v0.1.0 |
| 5 | Hybrid search (EN/DE) | `SearchModeToggle` (custom) | PR #37, search page |
| 6 | Interactive entity graph | `EntityGraphMini` | PR #32, graph page |
| 7 | SOP gated workflows | `SOPGateChain` | SOPs page, v0.1.0 |
| 8 | SharePoint Graph integration | `SharePointSync` (custom) | v0.2.0 SharePoint Graph |
| 9 | Matter scoping (multi-tenant) | `MatterScopeFork` | PR #35, matters page |

**Suggested release cadence:** one teaser per week, in the order above. Teaser
#1 (universal pain) → #2 (most surprising voice feature) → #3 (compliance
hook for risk officers) → ... → #9 (multi-tenant for larger firms).

**Dependency-aware ordering:** #1 also unblocks #2 (both use `VoiceWaveformDemo`).
#3 and #4 are paired (routing → audit chain) and could ship in the same week
as a "compliance double-feature." #5 is independent. #6 depends on a screen
capture from `/graph`. #7 needs a mocked SOP YAML for the demo. #8 needs a
SharePoint screen-capture frame.

---

## 12. Open Questions / Risks

These do not block teaser #1 but flag them at Phase 3:

1. **Audio narration (deferred to series v2)** — entire series ships silent
   in v1. v2 could add voice-over via ElevenLabs if Craig wants narrated
   versions for embed contexts that need them.
2. **DE multilingual variants (deferred to series v2)** — Swiss firms work
   in DE more than EN. Either burned-in DE subtitles or full DE re-record.
3. **6% pain-statistic citation (this teaser)** — resolved via §6 Q4. Default
   to descriptive statement.
4. **Brand approval from Craig** — recommend running teaser #1 by Craig
   (Slack DM `D0ALWJRGBQB`) before public embed. Internal review only;
   does not block render.
5. **Hosting / distribution** — chiefofstaff.pro CDN? Cloudinary? GitHub
   Releases? Decide once teaser #1 is rendered and Craig approves visually.
6. **Series cadence** — one per week, or all 9 in one go? Recommendation:
   render #1 now, V>> + Craig review, then decide cadence based on response.

---

## 13. References

- Remotion skill: `~/.claude/skills/remotion-video-creation/SKILL.md` (v2.0.0)
- Remotion runtime: `~/CodeTonight/grip-remotion-demo/`
- Time-entries frontend: `~/nexus-poc/frontend/src/app/(main)/time/page.tsx`
- Time-entries backend: `~/nexus-poc/backend/app/routes.py:832-893`
- NEXUS brand tokens: `~/nexus-poc/frontend/src/app/globals.css`
- CHANGELOG anchors: `~/nexus-poc/CHANGELOG.md` (v0.1.0 voice time, v0.2.0 transcript persistence)
- Project identity: `~/nexus-poc/CLAUDE.md`
- Tagline source: `~/nexus-poc/CLAUDE.md:6`

---

**Plan status:** ready for the future session.

Future session opens with Phase 0 override AskUser (§1), proceeds through
Phase 3 confirmations (§6), then silently builds and renders teaser #1 per
§2, §3, §5, §7 against the acceptance criteria in §8. On successful ship,
the same session (or a follow-up) can render teasers #2–9 against §11
roadmap, reusing the foundation laid in §5 and §1.5.
