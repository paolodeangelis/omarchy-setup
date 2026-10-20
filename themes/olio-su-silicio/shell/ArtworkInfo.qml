pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons

Item {
  id: root

  property string background: ""
  property string metadataPath: ""
  property var metadata: ({})

  function value(name) {
    const candidate = metadata[name]
    const text = candidate === undefined ? "" : String(candidate).trim()
    return text === "" || text.toLowerCase() === "unknown" ? "[unknown]" : text
  }

  function artist() {
    let name = value("artist")
    const attributed = name.toLowerCase().startsWith("attributed to ")
      || String(metadata.identification || "").toLowerCase() === "unverified"
    name = name.replace(/^Attributed to /i, "")
    return attributed && name !== "[unknown]" ? name + " (attributed)" : name
  }

  function refreshBackground(path) {
    path = path.trim()
    if (path === "" || path === background) return
    background = path
    metadataPath = path.replace(/\.[^/.]+$/, ".json")
    metadataFile.reload()
  }

  Process {
    id: backgroundLink
    command: ["readlink", "-f", Quickshell.env("HOME") + "/.local/state/omarchy/current/background"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.refreshBackground(text)
    }
  }

  Timer {
    interval: 1000
    repeat: true
    running: true
    triggeredOnStart: true
    onTriggered: if (!backgroundLink.running) backgroundLink.running = true
  }

  Process {
    id: nextBackground
    command: ["omarchy", "theme", "bg", "next"]
  }

  Timer {
    interval: 24 * 60 * 60 * 1000
    repeat: true
    running: true
    onTriggered: if (!nextBackground.running) nextBackground.running = true
  }

  FileView {
    id: metadataFile
    path: root.metadataPath
    watchChanges: true
    printErrors: false
    onLoaded: {
      try { root.metadata = JSON.parse(text()) }
      catch (error) { root.metadata = ({}) }
    }
    onLoadFailed: root.metadata = ({})
    onFileChanged: reload()
  }

  Variants {
    model: Quickshell.screens

    PanelWindow {
      id: panel
      required property var modelData
      screen: modelData
      visible: root.background !== ""
      anchors { top: true; bottom: true; left: true; right: true }
      color: "transparent"
      exclusionMode: ExclusionMode.Ignore
      WlrLayershell.namespace: "olio-artwork-info"
      WlrLayershell.layer: WlrLayer.Bottom
      WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
      mask: Region { item: infoStack }

      property bool expanded: false

      Item {
        id: infoStack
        width: panel.expanded ? 360 : 24
        height: panel.expanded ? card.height + 36 : 24
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: 28
        anchors.bottomMargin: 28

        Rectangle {
          id: card
          visible: panel.expanded
          width: 360
          height: details.implicitHeight + 32
          anchors.right: parent.right
          anchors.top: parent.top
          radius: 16
          color: "#ccffffff"
          opacity: panel.expanded ? 1 : 0
          Behavior on opacity { NumberAnimation { duration: 120 } }

          Text {
            id: details
            anchors.fill: parent
            anchors.margins: 16
            color: "#e6101420"
            wrapMode: Text.Wrap
            font.family: Style.font.family
            font.pixelSize: Style.font.body
            lineHeight: 1.2
            text: "Title: " + root.value("title")
              + "\nArtist: " + root.artist()
              + "\nYear: " + root.value("date")
              + "\nGallery: " + root.value("collection")
          }
        }

        Image {
          width: 24
          height: 24
          anchors.right: parent.right
          anchors.bottom: parent.bottom
          source: "ArtworkInfoIcon.svg"
          sourceSize.width: 24
          sourceSize.height: 24
          opacity: panel.expanded ? 0.8 : 0.55
          Behavior on opacity { NumberAnimation { duration: 120 } }
        }

        MouseArea {
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onEntered: {
            closeTimer.stop()
            panel.expanded = true
          }
          onExited: closeTimer.restart()
        }

        Timer {
          id: closeTimer
          interval: 120
          onTriggered: panel.expanded = false
        }
      }
    }
  }
}
