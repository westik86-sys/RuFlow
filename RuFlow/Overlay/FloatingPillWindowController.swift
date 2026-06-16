import AppKit
import QuartzCore
import SwiftUI

enum FloatingPillPresentationError: LocalizedError {
    case contentViewMissing
    case notVisible
    case offScreen

    var errorDescription: String? {
        switch self {
        case .contentViewMissing:
            return "Не удалось показать индикатор диктовки"
        case .notVisible:
            return "Индикатор диктовки не появился"
        case .offScreen:
            return "Индикатор диктовки оказался за пределами экрана"
        }
    }
}

@MainActor
protocol DictationOverlayPresenting: AnyObject {
    var isVisibleOnScreen: Bool { get }

    @discardableResult
    func showRecording(
        message: String,
        level: Double,
        onStop: @escaping () -> Void,
        onCancel: @escaping () -> Void
    ) throws -> Bool

    func showLoader()
    func showError(message: String)
    func hide()
}

private final class NonActivatingFloatingPanel: NSPanel {
    override var canBecomeKey: Bool {
        false
    }

    override var canBecomeMain: Bool {
        false
    }

    override var acceptsFirstResponder: Bool {
        false
    }
}

@MainActor
final class FloatingPillWindowController: DictationOverlayPresenting {
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
        window = NonActivatingFloatingPanel(
            contentRect: NSRect(x: 0, y: 0, width: recordingWidth, height: standardHeight),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )

        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.level = .statusBar
        window.ignoresMouseEvents = true
        window.hidesOnDeactivate = false
        window.isReleasedWhenClosed = false
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        window.contentView = NSHostingView(rootView: FloatingPillView(state: state))
    }

    var isVisibleOnScreen: Bool {
        window.contentView != nil
            && window.isVisible
            && !window.frame.isEmpty
            && Self.screenIntersectsWindowFrame(window.frame)
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
    ) throws -> Bool {
        state.showRecording(
            message: message,
            level: level,
            onStop: onStop,
            onCancel: onCancel
        )
        positionWindowIfNeeded(width: recordingWidth, height: standardHeight, animated: false)
        window.ignoresMouseEvents = true

        if !window.isVisible || !isVisibleOnScreen {
            window.orderFrontRegardless()
        }

        try verifyVisibleOnScreen()
        return true
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
        let visibleFrame = Self.currentVisibleFrame()
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

    private func verifyVisibleOnScreen() throws {
        guard window.contentView != nil else {
            throw FloatingPillPresentationError.contentViewMissing
        }

        guard window.isVisible else {
            throw FloatingPillPresentationError.notVisible
        }

        guard Self.screenIntersectsWindowFrame(window.frame) else {
            throw FloatingPillPresentationError.offScreen
        }
    }

    private static func currentVisibleFrame() -> NSRect {
        let mouseLocation = NSEvent.mouseLocation
        if let screen = NSScreen.screens.first(where: { $0.frame.contains(mouseLocation) }) {
            return screen.visibleFrame
        }

        return NSScreen.main?.visibleFrame ?? NSScreen.screens.first?.visibleFrame ?? .zero
    }

    private static func screenIntersectsWindowFrame(_ frame: NSRect) -> Bool {
        NSScreen.screens.contains { screen in
            screen.frame.intersects(frame)
        }
    }
}
