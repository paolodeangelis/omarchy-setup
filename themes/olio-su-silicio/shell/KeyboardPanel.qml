import QtQuick
import Quickshell
import Quickshell.Wayland
import Caelestia.Blobs
import qs.Commons

// Layer-shell popup attached to a bar widget icon, designed for
// click-driven AND keyboard-driven panels (e.g. SUPER+CTRL+W summon).
//
// Built on PanelWindow with a brief WlrKeyboardFocus.Exclusive prime followed
// by OnDemand rather than PopupWindow (xdg-popup). The prime acquires focus
// both when the surface maps and when it reopens while still mapped for its
// fade-out. xdg-popups don't get that — they only receive keys after a
// click/hover routes focus through their parent surface — so keyboard-summoned
// popups fell flat without it.
//
// Exclusive would also grant map-time focus, but it makes Hyprland route
// *every* pointer event to the exclusive surface no matter which output
// the cursor is over, which leaves clicks on any other monitor unable to
// reach the dismissal surfaces below.
//
// API is a subset of Common.PopupCard: anchorItem, owner, bar, open,
// padding, margin, contentWidth/Height, centerOnBar, default contentItem.
// Missing on purpose (for now): triggerMode ("hover"), containsMouse.
//
// Positioning: full-screen layer-shell with the card placed inside at
// `cardOrigin`. We use the bar window's height/width for the perpendicular
// axis (away-from-bar) because mapToItem on the anchor returns
// bar-content-relative coords with internal layout offsets baked in
// (e.g. ~13px from the bar's vertical centering of its widget row). The
// parallel axis (along-the-bar) uses the anchor's content x/y since the
// bar spans full screen on that axis.
//
// Outside-click dismissal: an overlay MouseArea catches clicks, with the
// QsWindow.mask subtracting the bar strip so clicks on the bar still
// reach the bar widgets (activePopout coordinator hands off to another
// popup if the user clicks a different bar icon).
PanelWindow {
  id: root

  required property Item anchorItem
  required property QtObject bar
  property var owner: null
  property int margin: Style.gapsOut
  property int padding: Style.spacing.popupPadding
  property int contentWidth: Style.space(280)
  property int contentHeight: Style.space(200)
  property var borderSpec: Border.surfaceSpec("popups", "border", Color.popups.border, Math.max(1, Style.space(2)))
  property bool centerOnBar: false
  property bool open: false
  property int gap: bar && bar.barMargins && bar.barMargins.floating === true
    ? Math.max(0, Number(bar.barMargins.popupGap) || 0)
    : Math.max(6, Style.gapsOut)  // distance between bar edge and panel
  property bool popoutSwitching: false
  property bool popoutSwitchClosing: false
  property bool focusPrimed: false
  property bool spatialAnimationEnabled: false
  property bool visualOpenPending: false
  property real visualX: 0
  property real visualY: 0
  property real visualWidth: 1
  property real visualHeight: 1
  readonly property real liquidSmoothing: Math.max(28, Style.cornerRadius * 2)
  readonly property int spatialDuration: 300

  // Item that should take keyboard focus once the panel maps. Typically a
  // PanelKeyCatcher inside the panel content. Layer-shell grants focus to the
  // surface during the Exclusive prime, but Qt still needs an active-focus
  // target inside the surface for Keys.onPressed handlers to fire. Schedule
  // the focus through Qt.callLater so it runs after the surface is fully
  // mapped and child items have completed layout.
  property Item focusTarget: null

  default property alias contentItem: contentHolder.children

  readonly property var coordinatorKey: owner || root
  readonly property var anchorWindow: anchorItem ? anchorItem.QsWindow.window : null
  readonly property string barPos: bar ? bar.position : "top"

  function close() {
    if (owner && "close" in owner) owner.close()
    else root.open = false
  }

  function beginFocusPrime() {
    if (open && backingWindowVisible) focusPrimeTimer.restart()
  }

  // --- screen + lifetime ---------------------------------------------------

  screen: anchorWindow ? anchorWindow.screen : null
  visible: open || card.opacity > 0 || popoutSwitching
  color: "transparent"
  exclusionMode: ExclusionMode.Ignore

  WlrLayershell.namespace: "omarchy-keyboard-panel"
  WlrLayershell.layer: WlrLayer.Overlay
  // Keyboard focus follows `open` (NOT `visible`). The window remains
  // mapped during the fade-out so the opacity animation has something to
  // animate, but keyboard/click ownership must release the moment the
  // logical close fires — otherwise the user is locked out for 140ms.
  //
  // Prime with Exclusive on every open, then settle on OnDemand. Hyprland
  // focuses OnDemand when a surface first maps, but not when an already-mapped
  // fade-out surface changes from None back to OnDemand. Exclusive also takes
  // focus when the previously focused application has constrained the pointer.
  // The brief prime covers both cases; OnDemand then releases compositor-wide
  // pointer hit-testing so clicks can reach the dismissal windows below.
  WlrLayershell.keyboardFocus: open
    ? (focusPrimed ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.Exclusive)
    : WlrKeyboardFocus.None

  onBackingWindowVisibleChanged: {
    beginFocusPrime()
    startPendingVisualOpen()
  }

  // Full-screen layer-shell. The visible card is positioned inside via
  // `cardOrigin`. The `mask` below makes the bar area click-through (so
  // the user can click another bar icon while the panel is open and the
  // activePopout coordinator swaps to that popup); everywhere else, the
  // overlay catches the click and dismisses via the MouseArea below.
  anchors {
    top: true
    bottom: true
    left: true
    right: true
  }

  // Clickable region is the whole screen. Clicks in the bar strip are
  // forwarded to registered bar buttons so switching between panel icons
  // works in one click even when the overlay surface is above the bar.
  readonly property real _barStripSize: {
    if (!bar) return 0
    var actual = (root.barPos === "top" || root.barPos === "bottom") ? root.barH : root.barW
    return Math.max(bar.barSize, actual) + root.gap
  }
  mask: Region {
    width: root.screenW
    height: root.screenH
  }

  // Track every layout change between the bar's contentItem and the
  // anchor item. `transform` updates whenever any item in that chain
  // moves/resizes, which is what makes the position binding below
  // actually reactive — mapToItem on its own is a one-shot.
  TransformWatcher {
    id: anchorWatcher
    a: anchorWindow ? anchorWindow.contentItem : null
    b: anchorItem
  }

  // Anchor item's position within the bar's content surface. For a
  // full-width top bar, the content x maps directly to screen x; the y
  // returned here has the bar's internal padding baked in (e.g. ~13px
  // from vertical centering of the widget row), which is why `cardOrigin`
  // below uses `barH` for the perpendicular axis instead of this y.
  readonly property point anchorScreenPos: {
    anchorWatcher.transform  // reactive dependency
    if (!anchorItem || !anchorWindow) return Qt.point(0, 0)
    var p = anchorItem.mapToItem(anchorWindow.contentItem, 0, 0)
    return Qt.point(p.x + barX, p.y + barY)
  }
  readonly property real anchorW: anchorItem ? anchorItem.width : 0
  readonly property real anchorH: anchorItem ? anchorItem.height : 0
  readonly property real screenW: screen ? screen.width : 0
  readonly property real screenH: screen ? screen.height : 0
  readonly property real availableCardWidth: screenW > 0
    ? Math.max(120, screenW - ((barPos === "left" || barPos === "right") ? barW + gap + margin : margin * 2))
    : 0
  readonly property real availableCardHeight: screenH > 0
    ? Math.max(120, screenH - ((barPos === "top" || barPos === "bottom") ? barH + gap + margin : margin * 2))
    : 0
  readonly property real verticalContentInset: padding * 2 + Border.top(borderSpec) + Border.bottom(borderSpec)

  function fittedContentWidth(width, cap) {
    var desired = Math.max(1, Number(width) || 1)
    var maxWidth = root.availableCardWidth > 0 ? root.availableCardWidth : desired
    if (cap !== undefined && Number(cap) > 0) maxWidth = Math.min(maxWidth, Number(cap))
    return Math.round(Math.min(desired, maxWidth))
  }

  function fittedContentHeight(implicitHeight, cap) {
    var desired = Math.max(root.verticalContentInset, (Number(implicitHeight) || 0) + root.verticalContentInset)
    var maxHeight = root.availableCardHeight > 0 ? root.availableCardHeight : desired
    if (cap !== undefined && Number(cap) > 0) maxHeight = Math.min(maxHeight, Number(cap))
    return Math.round(Math.min(desired, maxHeight))
  }

  function cappedContentHeight(height) {
    var desired = Math.max(root.padding * 2, Number(height) || root.padding * 2)
    var maxHeight = root.availableCardHeight > 0 ? root.availableCardHeight : desired
    return Math.round(Math.min(desired, maxHeight))
  }

  // Desired top-left of the card in screen coordinates. For the
  // perpendicular axis (away-from-bar) we anchor to the bar window's edge
  // directly — not the anchor item's y/x — because mapToItem(barContent)
  // returns coordinates in the bar's content space, which can be offset
  // from the bar surface's screen-anchored corner by internal layout
  // (centering wrappers, padding). The bar's surface IS aligned to its
  // anchored screen edge, so using `barW`/`barH` gives the right edge
  // regardless of how the bar's internal widgets are positioned. For the
  // parallel axis (along the bar) the anchor item's reported position is
  // still consistent with the bar content origin, so it's accurate for
  // centering the card under the icon.
  readonly property real barW: anchorWindow ? anchorWindow.width : screenW
  readonly property real barH: anchorWindow ? anchorWindow.height : 0
  readonly property var barMargins: bar && bar.barMargins ? bar.barMargins : ({ top: 0, right: 0, bottom: 0, left: 0 })
  readonly property real barEdgeMargin: barMargins[barPos] || 0
  readonly property real barX: barPos === "right" ? screenW - barW : 0
  readonly property real barY: barPos === "bottom" ? screenH - barH : 0
  // `barMargins` is an Olio host extension. Stock Omarchy's PluginBarApi does
  // not expose it, so the shared popup must remain a normal stock card there.
  readonly property bool hasOlioBarGeometry: !!bar && bar.barMargins !== undefined
  readonly property bool liquidEnabled: hasOlioBarGeometry && barPos === "top"
    && barMargins.top === 0 && barMargins.right === 0
    && barMargins.bottom === 0 && barMargins.left === 0
  // A liquid card is merged into the fixed bar only while it can physically
  // fit inside that bar. Wide panels (the notification centre is the usual
  // example) must retain normal screen-wide clamping; constraining an
  // oversized card to the island produces an inverted range and pins it to
  // the island's left edge.
  readonly property bool liquidCardFitsBar: liquidEnabled && contentWidth <= barW
  readonly property point cardOrigin: {
    if (!anchorItem || !bar) return Qt.point(margin, margin)
    var x = 0, y = 0
    if (centerOnBar && (barPos === "top" || barPos === "bottom")) {
      x = barX + barW / 2 - contentWidth / 2
      y = barPos === "bottom" ? barY - contentHeight - gap : barY + barH + gap
    } else if (centerOnBar) {
      x = barPos === "left" ? barX + barW + gap : barX - contentWidth - gap
      y = barY + barH / 2 - contentHeight / 2
    } else if (barPos === "bottom") {
      x = anchorScreenPos.x + anchorW / 2 - contentWidth / 2
      y = barY - contentHeight - gap
    } else if (barPos === "left") {
      x = barX + barW + gap
      y = anchorScreenPos.y + anchorH / 2 - contentHeight / 2
    } else if (barPos === "right") {
      x = barX - contentWidth - gap
      y = anchorScreenPos.y + anchorH / 2 - contentHeight / 2
    } else { // "top" (default)
      x = anchorScreenPos.x + anchorW / 2 - contentWidth / 2
      y = barY + barH + gap
    }
    // A floating horizontal bar can sit farther in from the screen edge than
    // the popup's ordinary outer margin. Keep the card inside the bar's real
    // horizontal bounds so edge popouts terminate flush with the island
    // instead of protruding by the margin difference.
    var minX = margin
    var maxX = screenW - contentWidth - margin
    if (liquidCardFitsBar && (barPos === "top" || barPos === "bottom")) {
      minX = Math.max(minX, barX)
      maxX = Math.min(maxX, barX + barW - contentWidth)
    }
    x = Math.max(minX, Math.min(x, maxX))
    y = Math.max(margin, Math.min(y, screenH - contentHeight - margin))
    return Qt.point(Math.round(x), Math.round(y))
  }

  function transitionGeometry() {
    if (!bar || typeof bar.popoutTransitionFor !== "function") return null
    return bar.popoutTransitionFor(screen ? screen.name : "")
  }

  function reportVisualGeometry() {
    if (!open || !liquidCardFitsBar || !bar || typeof bar.reportPopoutGeometry !== "function") return
    bar.reportPopoutGeometry(coordinatorKey, {
      screenName: screen ? screen.name : "",
      x: visualX, y: visualY, width: visualWidth, height: visualHeight
    })
  }

  function settleVisualGeometry() {
    visualX = cardOrigin.x
    // liquidViewport already starts at the top bar's lower edge. Keep both
    // fixed and floating top-bar cards in that local coordinate space; using
    // cardOrigin.y here adds bar height twice and enlarges the configured gap.
    visualY = barPos === "top" ? gap : cardOrigin.y
    visualWidth = contentWidth
    visualHeight = contentHeight
  }

  function beginVisualOpen(previous) {
    spatialAnimationEnabled = false
    if (liquidCardFitsBar && previous
        && Number(previous.width) > 0 && Number(previous.height) > 0) {
      visualX = Number(previous.x)
      visualY = Number(previous.y)
      visualWidth = Number(previous.width)
      visualHeight = Number(previous.height)
    } else {
      visualX = cardOrigin.x
      visualWidth = contentWidth
      visualHeight = contentHeight
      visualY = liquidCardFitsBar
        ? -visualHeight
        : (barPos === "top" ? gap : cardOrigin.y)
    }
    visualOpenPending = true
    startPendingVisualOpen()
  }

  function startPendingVisualOpen() {
    if (!visualOpenPending || !open || !backingWindowVisible) return
    visualOpenPending = false
    Qt.callLater(function() {
      if (!root.open) return
      root.spatialAnimationEnabled = root.liquidCardFitsBar
      root.settleVisualGeometry()
    })
  }

  onCardOriginChanged: if (open && !popoutSwitching) settleVisualGeometry()
  onContentWidthChanged: if (open && !popoutSwitching) settleVisualGeometry()
  onContentHeightChanged: if (open && !popoutSwitching) settleVisualGeometry()
  onVisualXChanged: reportVisualGeometry()
  onVisualYChanged: reportVisualGeometry()
  onVisualWidthChanged: reportVisualGeometry()
  onVisualHeightChanged: reportVisualGeometry()


  // --- popout coordination (same-bar single-popout model) -----------------

  // Coordinate on `open`, not `visible`. `visible` lags into the fade-out
  // animation, which made ownership transfer to a sibling popup race.
  onOpenChanged: {
    if (open) {
      focusPrimed = false
      beginFocusPrime()
      if (focusTarget) Qt.callLater(function() {
        if (root.open && root.focusTarget) root.focusTarget.forceActiveFocus()
      })
    } else {
      focusPrimeTimer.stop()
      focusPrimed = false
      visualOpenPending = false
    }
    if (!bar) return
    if (open) {
      popoutSwitchClosing = false
      popoutSwitching = bar.activePopout && bar.activePopout !== coordinatorKey
      var previousGeometry = popoutSwitching ? transitionGeometry() : null
      bar.requestPopout(coordinatorKey)
      beginVisualOpen(previousGeometry)
      if (popoutSwitching) popoutSwitchTimer.restart()
    } else {
      popoutSwitchClosing = !!(owner && owner.popoutSwitchClosing)
      popoutSwitching = false
      spatialAnimationEnabled = liquidCardFitsBar && !popoutSwitchClosing
      if (spatialAnimationEnabled) visualY = -visualHeight
      if (bar.activePopout === coordinatorKey) bar.releasePopout(coordinatorKey)
      if (popoutSwitchClosing) closeSwitchTimer.restart()
    }
  }

  Timer {
    id: focusPrimeTimer
    // Leave enough time for multiple Qt/Wayland commit cycles after the
    // backing window becomes visible while keeping the compositor-wide
    // Exclusive phase imperceptibly short. This interval is covered by the
    // immediate hide/re-summon acceptance case.
    interval: 75
    onTriggered: if (root.open) root.focusPrimed = true
  }

  Timer {
    id: popoutSwitchTimer
    interval: root.spatialDuration
    onTriggered: root.popoutSwitching = false
  }

  Timer {
    id: closeSwitchTimer
    // Keep the old background mapped until the incoming Wayland surface has
    // presented its first frame. Its content fades immediately below.
    interval: 60
    onTriggered: root.popoutSwitchClosing = false
  }

  // --- outside-click dismissal --------------------------------------------

  // Catches clicks anywhere in the clickable region (i.e. everywhere on
  // screen except the bar strip, which is masked out). The card has its
  // own MouseArea below so clicks on it don't bubble up here. Disabled
  // during the fade-out so the dying overlay doesn't swallow clicks that
  // were meant for the apps behind it.
  MouseArea {
    id: dismissArea
    anchors.fill: parent
    enabled: root.open
    acceptedButtons: Qt.AllButtons
    hoverEnabled: true
    property bool hoveringBar: false
    cursorShape: hoveringBar ? Qt.PointingHandCursor : Qt.ArrowCursor

    function inBarRegion(px, py) {
      if (root.barPos === "bottom") return py >= root.screenH - root._barStripSize
      if (root.barPos === "left") return px <= root._barStripSize
      if (root.barPos === "right") return px >= root.screenW - root._barStripSize
      return py <= root._barStripSize
    }

    function barPoint(px, py) {
      return Qt.point(px - root.barX, py - root.barY)
    }

    function pressTargetAt(px, py) {
      if (!root.anchorWindow || !root.anchorWindow.contentItem || !root.bar || !root.bar.clickTargets) return null
      var p = barPoint(px, py)
      var targets = root.bar.clickTargets
      for (var i = targets.length - 1; i >= 0; i--) {
        var target = targets[i]
        if (!target || !target.triggerPress || target.visible === false || target.opacity === 0 || !target.mapToItem) continue
        if (root.bar.targetBelongsToWindow && !root.bar.targetBelongsToWindow(target, root.anchorWindow)) continue
        var pos = root.anchorWindow.itemPosition(target)
        if (p.x >= pos.x && p.x <= pos.x + target.width && p.y >= pos.y && p.y <= pos.y + target.height) return target
      }
      return null
    }

    function forwardBarClick(px, py, button) {
      if (button !== Qt.LeftButton && button !== Qt.RightButton && button !== Qt.MiddleButton) return false
      var target = pressTargetAt(px, py)
      if (!target) return false
      target.triggerPress(button)
      return true
    }

    onPositionChanged: function(mouse) { hoveringBar = inBarRegion(mouse.x, mouse.y) }
    onExited: hoveringBar = false
    onClicked: function(mouse) {
      // While Exclusive is priming, Hyprland may route a click from another
      // output here with translated coordinates. Never interpret that as a
      // click on this output's bar.
      if (root.focusPrimed && inBarRegion(mouse.x, mouse.y) && forwardBarClick(mouse.x, mouse.y, mouse.button)) return
      root.close()
    }
  }

  // The panel surface only spans the anchor's screen, and the compositor
  // hit-tests pointer input per output, so `dismissArea` above can never see
  // a click on another monitor. Give every other output a transparent twin
  // whose only job is to catch that click. They exist only while the panel is
  // logically open (not during the fade-out, matching `dismissArea.enabled`).
  //
  // Keyboard focus is None: these must catch the pointer without taking focus
  // from the panel when the cursor merely crosses onto their output.
  Variants {
    model: root.open ? Quickshell.screens : []

    delegate: Component {
      PanelWindow {
        required property var modelData

        screen: modelData
        // Compare by output name: the anchor screen must be known before any
        // twin maps, or a twin would cover the panel's own output.
        visible: root.open && !!root.screen && modelData.name !== root.screen.name
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore

        WlrLayershell.namespace: "omarchy-keyboard-panel-dismiss"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

        anchors {
          top: true
          bottom: true
          left: true
          right: true
        }

        MouseArea {
          anchors.fill: parent
          acceptedButtons: Qt.AllButtons
          onPressed: root.close()
        }
      }
    }
  }

  // --- card ----------------------------------------------------------------

  Item {
    id: liquidViewport
    x: 0
    y: root.barPos === "top" ? root.barY + root.barH : 0
    width: root.screenW
    height: root.barPos === "top" ? Math.max(0, root.screenH - y) : root.screenH
    clip: root.barPos === "top"

    BlobGroup {
      id: liquidGroup
      color: Color.popups.background
      smoothing: root.liquidSmoothing
      cornerFill: true
    }

    // Model the complete bar surface above the clip boundary. Its padded SDF
    // reaches below the real bar edge and merges with the moving panel, while
    // clipping leaves the actual bar and its widgets visible.
    BlobRect {
      id: liquidBarSurface
      x: root.barX
      y: -root.barH
      width: root.barW
      height: root.barH
      // The group is what lets the card fuse with the fixed bar. Floating
      // cards stay independent, so the same BlobRect renders as a normal
      // rounded card instead of retaining the liquid corner treatment.
      group: root.liquidCardFitsBar ? liquidGroup : null
      radius: bar && bar.islandRadius !== undefined ? bar.islandRadius : 0
      visible: root.liquidCardFitsBar && card.opacity > 0
    }

    Rectangle {
      id: floatingCardSurface
      x: card.x
      y: card.y
      width: card.width
      height: card.height
      visible: !root.liquidCardFitsBar && card.opacity > 0
      color: Color.popups.background
      radius: Math.max(16, Style.cornerRadius)
      border.width: Border.top(root.borderSpec)
      border.color: Border.color(root.borderSpec)
    }

    BlobRect {
      id: card
      readonly property real targetX: root.cardOrigin.x
      readonly property real targetY: root.barPos === "top" ? root.gap : root.cardOrigin.y
      x: root.visualX
      y: root.visualY
      width: root.visualWidth
      height: root.visualHeight
      group: root.liquidCardFitsBar ? liquidGroup : null
      radius: Math.max(16, Style.cornerRadius)
      deformScale: 0.00002
      opacity: root.open || root.popoutSwitching || root.popoutSwitchClosing ? 1.0 : 0

      Behavior on x {
        enabled: root.liquidCardFitsBar && root.spatialAnimationEnabled
        NumberAnimation {
          duration: root.spatialDuration
          easing.type: Easing.BezierSpline
          easing.bezierCurve: [0.38, 1.05, 0.22, 1, 1, 1]
        }
      }

      Behavior on y { enabled: root.liquidCardFitsBar && root.spatialAnimationEnabled; NumberAnimation {
        duration: root.open ? root.spatialDuration : 180
        easing.type: Easing.BezierSpline
        easing.bezierCurve: root.open ? [0.38, 1.05, 0.22, 1, 1, 1] : [0.4, 0, 1, 1, 1, 1]
      } }
      Behavior on width { enabled: root.liquidCardFitsBar && root.spatialAnimationEnabled; NumberAnimation {
        duration: root.spatialDuration; easing.type: Easing.BezierSpline
        easing.bezierCurve: [0.38, 1.05, 0.22, 1, 1, 1]
      } }
      Behavior on height { enabled: root.liquidCardFitsBar && root.spatialAnimationEnabled; NumberAnimation {
        duration: root.spatialDuration; easing.type: Easing.BezierSpline
        easing.bezierCurve: [0.38, 1.05, 0.22, 1, 1, 1]
      } }

      Behavior on opacity {
        enabled: !root.popoutSwitching && !root.popoutSwitchClosing
        NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
      }

      // Swallow clicks on the card so they don't bubble to the dismissal
      // MouseArea behind us.
      MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
      }

      Item {
        id: contentHolder
        anchors.fill: parent
        anchors.margins: root.padding
        opacity: root.open ? 1.0 : 0.0

        transform: Matrix4x4 { matrix: card.deformMatrix }

        Behavior on opacity {
          enabled: root.popoutSwitching || root.popoutSwitchClosing
          NumberAnimation { duration: 70; easing.type: Easing.OutCubic }
        }
      }
    }
  }
}
