import AppKit
import SwiftUI

@MainActor
final class FloatingPillWindowController {
    private let window: NSPanel
    private let width: CGFloat = 240
    private let height: CGFloat = 64

    init() {
        window = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: width, height: height),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )

        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.level = .statusBar
        window.ignoresMouseEvents = true
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        window.contentView = NSHostingView(rootView: FloatingPillView(message: ""))
    }

    func show(message: String) {
        window.contentView = NSHostingView(rootView: FloatingPillView(message: message))
        positionWindow()
        window.orderFrontRegardless()
    }

    func hide() {
        window.orderOut(nil)
    }

    private func positionWindow() {
        let visibleFrame = NSScreen.main?.visibleFrame ?? NSScreen.screens.first?.visibleFrame ?? .zero
        let x = visibleFrame.midX - width / 2
        let y = visibleFrame.minY + 84
        window.setFrame(NSRect(x: x, y: y, width: width, height: height), display: true)
    }
}
