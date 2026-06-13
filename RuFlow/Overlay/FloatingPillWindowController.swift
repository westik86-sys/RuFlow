import AppKit
import QuartzCore
import SwiftUI

@MainActor
final class FloatingPillWindowController {
    private let window: NSPanel
    private let state = FloatingPillState()
    private let recordingWidth: CGFloat = 223
    private let loadingWidth: CGFloat = 65
    private let errorWidth: CGFloat = 383
    private let standardHeight: CGFloat = 65
    private let errorHeight: CGFloat = 89
    private var currentWidth: CGFloat?
    private var currentHeight: CGFloat?

    init() {
        window = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: recordingWidth, height: standardHeight),
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

    func showError(message: String) {
        state.showError(message)
        positionWindowIfNeeded(width: errorWidth, height: errorHeight, animated: false)
        window.ignoresMouseEvents = true
        window.orderFrontRegardless()
    }

    func showLoader() {
        state.showLoader()
        positionWindowIfNeeded(width: loadingWidth, height: standardHeight, animated: true)
        window.ignoresMouseEvents = true
        window.orderFrontRegardless()
    }

    func showRecording(
        message: String,
        level: Double,
        onStop: @escaping () -> Void,
        onCancel: @escaping () -> Void
    ) {
        state.showRecording(
            message: message,
            level: level,
            onStop: onStop,
            onCancel: onCancel
        )
        positionWindowIfNeeded(width: recordingWidth, height: standardHeight, animated: false)

        if !window.isVisible {
            window.ignoresMouseEvents = true
            window.orderFrontRegardless()
        }
    }

    func hide() {
        window.orderOut(nil)
        state.hide()
        currentWidth = nil
        currentHeight = nil
    }

    private func positionWindowIfNeeded(width: CGFloat, height: CGFloat, animated: Bool) {
        guard currentWidth != width || currentHeight != height || !window.isVisible else {
            return
        }

        positionWindow(width: width, height: height, animated: animated && window.isVisible)
    }

    private func positionWindow(width: CGFloat, height: CGFloat, animated: Bool) {
        let visibleFrame = NSScreen.main?.visibleFrame ?? NSScreen.screens.first?.visibleFrame ?? .zero
        let x = visibleFrame.midX - width / 2
        let y = visibleFrame.minY + 84
        let frame = NSRect(x: x, y: y, width: width, height: height)

        if animated {
            NSAnimationContext.runAnimationGroup { context in
                context.duration = 0.22
                context.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
                window.animator().setFrame(frame, display: true)
            }
        } else {
            window.setFrame(frame, display: true)
        }

        currentWidth = width
        currentHeight = height
    }
}
