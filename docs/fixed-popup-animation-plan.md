# Fixed popup motion: comparison and implementation plan

Source audit: 2026-09-29. Olio baseline: `e8e15a8`. Omacale:
`a213d722f9884192748249909506f71ccd2b6044`, manifest **0.39.0**.
This is a plan, not an animation implementation or a measured smoothness result.
No desktop configuration changed during this audit.

## What actually differs

| Mechanism | Omacale | Olio fixed baseline |
| --- | --- | --- |
| Background lifetime | Persistent per-screen frame and popup rectangle | Separate `KeyboardPanel` surfaces and blob groups |
| Opening | Animated offset slides clipped content from behind bar | Card Y slides, with independent opacity animation |
| Switching | Persistent width, height and along-bar position interpolate to new targets | X/width/height bind directly; switching disables Y animation and uses timed opacity handoff |
| Placement | Final content size determines target, separate from animated size | Each new panel computes its own target |
| Joining | One shader merges frame and attached rectangles with circular fillets | Each panel models a bar segment and card, below the real bar |
| Third-party panels | Separate compatibility hosting path | Existing plugin panels through version-sensitive overlay |

Evidence:

- [ScreenScope.qml](https://github.com/AyushKr2003/omacale/blob/a213d722f9884192748249909506f71ccd2b6044/omacale.bar/modules/drawers/ScreenScope.qml):
  `pOff` around line 469; `pw/ph/pa`, `pSettled`, `pAnimate` around 538–595;
  one shader around 746; retained `PopoutContent.lastName` around 1028.
  The 60ms settling timer addresses delayed layout on opening from closed;
  it is not evidence that copying that delay fixes our lifecycle.
- [Anim.qml](https://github.com/AyushKr2003/omacale/blob/a213d722f9884192748249909506f71ccd2b6044/omacale.bar/components/Anim.qml)
  and [Tk.qml](https://github.com/AyushKr2003/omacale/blob/a213d722f9884192748249909506f71ccd2b6044/omacale.bar/core/Tk.qml):
  shared spatial/effects curves; default spatial duration is 500ms times scale.
  A longer animation can look more continuous; shorter is not necessarily smoother.
- [blob.frag](https://github.com/AyushKr2003/omacale/blob/a213d722f9884192748249909506f71ccd2b6044/omacale.bar/shaders/blob.frag):
  circular smooth-min, edge attachment and corner treatment. The popup background
  extends behind the bar so its rendered join does not detach during movement.
- Olio [`KeyboardPanel.qml`](../themes/olio-su-silicio/shell/KeyboardPanel.qml):
  switching timers around 292; `BlobRect card` around 453; direct X/size bindings,
  Y behavior disabled during handoff, separate content fade. That explains why
  our current code cannot interpolate one persistent rectangle across panels.

Inference: persistent geometry plus coordinated clipping/lifetime is the useful
lesson—not adopting all of Omacale, increasing radius, or only changing easing.
The source supports this explanation; no equivalent-hardware video benchmark or
frame-by-frame measurement was performed. Do not claim measured superiority.

## Compatibility: important qualification

Omacale's built-in pages are its own
[PopoutContent](https://github.com/AyushKr2003/omacale/blob/a213d722f9884192748249909506f71ccd2b6044/omacale.bar/modules/bar/PopoutContent.qml).
Its [BarWidgetSlot](https://github.com/AyushKr2003/omacale/blob/a213d722f9884192748249909506f71ccd2b6044/omacale.bar/modules/bar/BarWidgetSlot.qml)
has a different path for third-party `KeyboardPanel`/`PopupCard`: object-tree
inspection and bindings correcting gap, placement, minimum width and radius.
Therefore its built-in animation is **not proof of automatic liquid motion for
every arbitrary Omarchy plugin**. Copying those internal probes would introduce
the same kind of version-sensitive coupling we want to constrain.

Its [installer](https://github.com/AyushKr2003/omacale/blob/a213d722f9884192748249909506f71ccd2b6044/scripts/omacale)
keeps snapshots and restores them on uninstall; optional notification/lock
handovers have recovery logic. Its
[contract checker](https://github.com/AyushKr2003/omacale/blob/a213d722f9884192748249909506f71ccd2b6044/scripts/upstream-check)
compares dependency hashes and bar member names against a lock; this detects
changes but does not prove runtime compatibility. Its fixture
[restore tests](https://github.com/AyushKr2003/omacale/blob/a213d722f9884192748249909506f71ccd2b6044/tests/test-restore.sh)
are not a substitute for booted upgrade/rendering tests. License is GPL-3.0;
retain attribution/license obligations if later borrowing implementation.

Correction to the previous comparison: the earlier 0.35.12/source mismatch was
time-specific. This inspected 0.39.0 revision implements edge-dependent geometry.
The Reddit 0.37 announcement alone remains insufficient compatibility evidence.

## Proposed work, in order

1. **Capture baseline in a disposable pinned VM.** Same scale, background,
   opacity and popup sequence. Test the actual radar bar click, not its standalone
   window. Establish current failures separately from proposed motion.
2. **Define one small fixed-mode lifecycle contract.** Per screen, expose stable
   panel identity, anchor, final content size, open/close state and ownership.
   Preserve scoped services, focus, Escape/Tab and dismiss behavior. Feature-detect
   it; unsupported hosts/panels use ordinary rounded detached popups. Keep this
   adapter isolated and version-checked, ideally upstreamable.
3. **Prototype persistent background only.** Retain current geometry during A→B;
   animate X/width/height from current interpolated values to B's final target.
   Opening from closed should start at the clicked anchor, not the previous
   panel's position. Wait for valid layout without relying on an arbitrary timer.
   Do not reparent arbitrary plugin content or replace its service facade.
4. **Coordinate presentation.** One owner decides background, clipping and
   content visibility. Remove the old handoff timers only after the equivalent
   behavior is proven. One effective surface colour/alpha must cover the join;
   overlapping translucent surfaces can produce a seam even with equal settings.
   If the existing separate content windows cannot follow reliably, stop the
   prototype and propose the necessary shared-host API—do not patch each plugin.
5. **Gate, then consider adoption.** Run pinned, latest and configured-upgrade
   VMs. Prove missing-capability fallback and full restore independently. Floating
   mode must stay unchanged. Only then request visual acceptance and implement
   the minimal reviewed patch. This task does not authorize steps 1–5 on the host.

## Required proof before calling it finished

- Closed→clock; clock→audio→network→notification; interrupt midway and reverse;
  repeated clicks; Escape/Tab; workspace switch while open; left/right edges;
  content resizing after load; actual radar preview and Spaces hover/settings.
- Record at a stated frame rate with timestamps. Inspect every transition frame
  for gaps, flashes, doubled backgrounds, clipping and unexpected origin jumps.
  Report dropped frames; don't infer them from a static screenshot.
- Test opaque and translucent settings. Keep geometry and colour baselines fixed
  while comparing motion. Verify no content painted outside its background.
- Preserve notifications/archive loading, launcher/menu and keyboard OSD. Require
  available logs and reject QML assignment/load errors. Test stock fallback and
  restoration without the custom API present.

Current blockers: no registered VM runner; actual radar/Spaces interaction driver
and animation recordings remain missing. Existing local visual acceptance is
valuable but does not establish future-update compatibility.
