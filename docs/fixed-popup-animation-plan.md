# Fixed popup motion: comparison, implementation, and evidence

Source audit: 2026-09-29. Olio baseline: `e8e15a8`. Omacale:
`a213d722f9884192748249909506f71ccd2b6044`, manifest **0.39.0**.
The comparison below motivated a narrow Olio implementation. It is not an
Omacale port and does not claim equivalent rendering architecture.

## What actually differs

| Mechanism | Omacale | Olio fixed baseline |
| --- | --- | --- |
| Background lifetime | Persistent per-screen frame and popup rectangle | Separate `KeyboardPanel` surfaces; the last numeric rectangle is retained by the bar |
| Opening | Animated offset slides clipped content from behind bar | Card Y slides, with independent opacity animation |
| Switching | Persistent width, height and along-bar position interpolate to new targets | The incoming surface starts at the retained rectangle and interpolates X/Y/width/height; the outgoing background is retained briefly for presentation handoff |
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
- Olio [`KeyboardPanel.qml`](../themes/olio-su-silicio/shell/KeyboardPanel.qml)
  stores only finite numeric geometry through the scoped bar API. Plugin content
  and service objects stay in their existing owners. Floating mode bypasses this
  fixed-only transition path.

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

## Implemented scope

The Olio bar now retains the last rendered fixed-popup rectangle per screen.
`KeyboardPanel` feature-detects that scoped API and animates the incoming card
from the retained X/Y/width/height to its own target. A 60ms background-only
handoff bridges creation of the new Wayland surface; plugin content fades
independently. No plugin source is patched or reparented. The overlay installer
adds the two optional API functions only after its existing fingerprint checks.

Floating mode keeps detached rounded popups and does not use retained liquid
geometry. A regression assertion protects its literal top-bar gap from adding
the bar height twice.

## Evidence and remaining proof

- Local 60fps recording exercised closed→clock and rapid
  clock→audio→network→audio reversal. A 20fps contact sheet showed no empty
  background frame or restart from the top.
- Fixed Notification Center, Spaces preview, OSD, and Super+Escape menu were
  visually checked. `doctor --ui` passed all 12 menu routes and the OSD smoke.
- Floating mode was reapplied and visually checked after the gap regression fix;
  fixed mode was restored as the active default.
- Test opaque and translucent settings. Keep geometry and colour baselines fixed
  while comparing motion. Verify no content painted outside its background.
- Pinned/latest/configured-upgrade VM acceptance, actual pointer-driven radar
  preview and Spaces hover, translucent comparisons, Tab/repeated-click stress,
  multi-output behavior, and stock fallback/restoration remain required before
  claiming future-release compatibility.

The hosted KVM workflow now completes repository bootstrap, all program installs,
their idempotent repeat, theme activation, and live doctor startup in the guest.
Its next run exposed plugin-facade teardown errors plus null-style warnings also
present in the pristine 4.0.4 shell. Olio's teardown defects were fixed; only the
three exact stock panel properties are classified separately, while every other
QML/runtime error still fails acceptance. A passing rerun is still required.
Local evidence does not establish future-update compatibility.
