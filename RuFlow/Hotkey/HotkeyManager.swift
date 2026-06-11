import AppKit
import ApplicationServices
import Foundation

final class HotkeyManager {
    var onPress: (() -> Void)?
    var onRelease: (() -> Void)?
    var onCancel: (() -> Void)?

    private let spaceKeyCode: Int64 = 49
    private let escapeKeyCode: Int64 = 53
    private var eventTap: CFMachPort?
    private var globalKeyUpMonitor: Any?
    private var globalFlagsMonitor: Any?
    private var runLoopSource: CFRunLoopSource?
    private var releaseWatchdogTimer: Timer?
    private var isHotkeyDown = false
    private var isSessionActive = false

    deinit {
        stop()
    }

    func restart() -> Bool {
        stop()
        return start()
    }

    func start() -> Bool {
        guard eventTap == nil else {
            return true
        }

        let mask = CGEventMask(1 << CGEventType.keyDown.rawValue)
            | CGEventMask(1 << CGEventType.keyUp.rawValue)
            | CGEventMask(1 << CGEventType.flagsChanged.rawValue)

        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .defaultTap,
            eventsOfInterest: mask,
            callback: HotkeyManager.eventCallback,
            userInfo: Unmanaged.passUnretained(self).toOpaque()
        ) else {
            return false
        }

        let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
        CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: true)

        eventTap = tap
        runLoopSource = source
        startGlobalReleaseMonitors()
        return true
    }

    func stop() {
        if let eventTap {
            CGEvent.tapEnable(tap: eventTap, enable: false)
        }

        if let runLoopSource {
            CFRunLoopRemoveSource(CFRunLoopGetMain(), runLoopSource, .commonModes)
        }

        eventTap = nil
        runLoopSource = nil
        stopGlobalReleaseMonitors()
        stopReleaseWatchdog()
        isHotkeyDown = false
        isSessionActive = false
    }

    func markSessionInactive() {
        stopReleaseWatchdog()
        isSessionActive = false
        isHotkeyDown = false
    }

    private static let eventCallback: CGEventTapCallBack = { _, type, event, userInfo in
        guard let userInfo else {
            return Unmanaged.passUnretained(event)
        }

        let manager = Unmanaged<HotkeyManager>.fromOpaque(userInfo).takeUnretainedValue()
        return manager.handle(type: type, event: event)
    }

    private func handle(type: CGEventType, event: CGEvent) -> Unmanaged<CGEvent>? {
        if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
            if let eventTap {
                CGEvent.tapEnable(tap: eventTap, enable: true)
            }
            return Unmanaged.passUnretained(event)
        }

        let keyCode = event.getIntegerValueField(.keyboardEventKeycode)

        switch type {
        case .keyDown:
            return handleKeyDown(event: event, keyCode: keyCode)
        case .keyUp:
            return handleKeyUp(event: event, keyCode: keyCode)
        case .flagsChanged:
            return handleFlagsChanged(event: event)
        default:
            return Unmanaged.passUnretained(event)
        }
    }

    private func handleKeyDown(event: CGEvent, keyCode: Int64) -> Unmanaged<CGEvent>? {
        if keyCode == escapeKeyCode {
            cancelHotkeySession()
            return nil
        }

        guard keyCode == spaceKeyCode, event.flags.contains(.maskAlternate) else {
            return Unmanaged.passUnretained(event)
        }

        let isRepeat = event.getIntegerValueField(.keyboardEventAutorepeat) != 0
        if !isHotkeyDown && !isRepeat {
            isHotkeyDown = true
            isSessionActive = true
            startReleaseWatchdog()
            onPress?()
        }

        return nil
    }

    private func handleKeyUp(event: CGEvent, keyCode: Int64) -> Unmanaged<CGEvent>? {
        guard keyCode == spaceKeyCode, isHotkeyDown else {
            return Unmanaged.passUnretained(event)
        }

        releaseHotkeySession()
        return nil
    }

    private func handleFlagsChanged(event: CGEvent) -> Unmanaged<CGEvent>? {
        guard isHotkeyDown, !event.flags.contains(.maskAlternate) else {
            return Unmanaged.passUnretained(event)
        }

        releaseHotkeySession()
        return Unmanaged.passUnretained(event)
    }

    private func startGlobalReleaseMonitors() {
        stopGlobalReleaseMonitors()

        globalKeyUpMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyUp) { [weak self] event in
            guard let self else {
                return
            }

            let keyCode = event.keyCode
            DispatchQueue.main.async {
                self.handleGlobalKeyUp(keyCode: keyCode)
            }
        }

        globalFlagsMonitor = NSEvent.addGlobalMonitorForEvents(matching: .flagsChanged) { [weak self] event in
            guard let self else {
                return
            }

            let isOptionDown = event.modifierFlags.contains(.option)
            DispatchQueue.main.async {
                self.handleGlobalFlagsChanged(isOptionDown: isOptionDown)
            }
        }
    }

    private func stopGlobalReleaseMonitors() {
        if let globalKeyUpMonitor {
            NSEvent.removeMonitor(globalKeyUpMonitor)
        }

        if let globalFlagsMonitor {
            NSEvent.removeMonitor(globalFlagsMonitor)
        }

        globalKeyUpMonitor = nil
        globalFlagsMonitor = nil
    }

    private func handleGlobalKeyUp(keyCode: UInt16) {
        if keyCode == UInt16(escapeKeyCode) {
            cancelHotkeySession()
            return
        }

        guard keyCode == UInt16(spaceKeyCode) else {
            return
        }

        releaseHotkeySession()
    }

    private func handleGlobalFlagsChanged(isOptionDown: Bool) {
        guard !isOptionDown else {
            return
        }

        releaseHotkeySession()
    }

    private func startReleaseWatchdog() {
        stopReleaseWatchdog()

        let timer = Timer(timeInterval: 0.03, repeats: true) { [weak self] _ in
            self?.stopIfHotkeyWasPhysicallyReleased()
        }

        RunLoop.main.add(timer, forMode: .common)
        releaseWatchdogTimer = timer
    }

    private func stopReleaseWatchdog() {
        releaseWatchdogTimer?.invalidate()
        releaseWatchdogTimer = nil
    }

    private func stopIfHotkeyWasPhysicallyReleased() {
        guard isHotkeyDown else {
            stopReleaseWatchdog()
            return
        }

        let isSpaceDown = CGEventSource.keyState(
            .hidSystemState,
            key: CGKeyCode(spaceKeyCode)
        )
        let isOptionDown = CGEventSource.flagsState(.hidSystemState).contains(.maskAlternate)

        if !isSpaceDown || !isOptionDown {
            releaseHotkeySession()
        }
    }

    private func releaseHotkeySession() {
        guard isHotkeyDown else {
            return
        }

        stopReleaseWatchdog()
        isHotkeyDown = false
        isSessionActive = false
        onRelease?()
    }

    private func cancelHotkeySession() {
        stopReleaseWatchdog()
        isHotkeyDown = false
        isSessionActive = false
        onCancel?()
    }
}

extension HotkeyManager: @unchecked Sendable {}
