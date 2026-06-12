import AppKit
import SwiftUI

@MainActor
final class FloatingPillWindowController {
    private let window: NSPanel
    private let state = FloatingPillState()
    private let messageWidth: CGFloat = 240
    private let recordingWidth: CGFloat = 223
    private let height: CGFloat = 65
    private var currentWidth: CGFloat?

    init() {
        window = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: messageWidth, height: height),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )

        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.level = .statusBar
        window.ignoresMouseEvents = false
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        window.contentView = NSHostingView(rootView: FloatingPillView(state: state))
    }

    func show(message: String) {
        state.showMessage(message)
        positionWindowIfNeeded(width: messageWidth)
        window.ignoresMouseEvents = true
        window.orderFrontRegardless()
    }

    func showRecording(
        message: String,
        onStop: @escaping () -> Void,
        onCancel: @escaping () -> Void
    ) {
        state.showRecording(
            message: message,
            onStop: onStop,
            onCancel: onCancel
        )
        positionWindowIfNeeded(width: recordingWidth)
        window.ignoresMouseEvents = true
        window.orderFrontRegardless()
    }

    func hide() {
        window.orderOut(nil)
        currentWidth = nil
    }

    private func positionWindowIfNeeded(width: CGFloat) {
        guard currentWidth != width || !window.isVisible else {
            return
        }

        positionWindow(width: width)
    }

    private func positionWindow(width: CGFloat) {
        let visibleFrame = NSScreen.main?.visibleFrame ?? NSScreen.screens.first?.visibleFrame ?? .zero
        let x = visibleFrame.midX - width / 2
        let y = visibleFrame.minY + 84
        window.setFrame(NSRect(x: x, y: y, width: width, height: height), display: true)
        currentWidth = width
    }
}
