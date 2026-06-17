import AppKit
import ApplicationServices
import Foundation

struct HotkeyModifiers: OptionSet, Equatable, Sendable {
    let rawValue: Int

    static let control = HotkeyModifiers(rawValue: 1 << 0)
    static let option = HotkeyModifiers(rawValue: 1 << 1)
    static let shift = HotkeyModifiers(rawValue: 1 << 2)
    static let command = HotkeyModifiers(rawValue: 1 << 3)

    init(rawValue: Int) {
        self.rawValue = rawValue
    }

    init(eventModifierFlags flags: NSEvent.ModifierFlags) {
        var modifiers: HotkeyModifiers = []

        if flags.contains(.control) {
            modifiers.insert(.control)
        }

        if flags.contains(.option) {
            modifiers.insert(.option)
        }

        if flags.contains(.shift) {
            modifiers.insert(.shift)
        }

        if flags.contains(.command) {
            modifiers.insert(.command)
        }

        self = modifiers
    }

    init(cgEventFlags flags: CGEventFlags) {
        var modifiers: HotkeyModifiers = []

        if flags.contains(.maskControl) {
            modifiers.insert(.control)
        }

        if flags.contains(.maskAlternate) {
            modifiers.insert(.option)
        }

        if flags.contains(.maskShift) {
            modifiers.insert(.shift)
        }

        if flags.contains(.maskCommand) {
            modifiers.insert(.command)
        }

        self = modifiers
    }

    var displayName: String {
        displayNameComponents.joined(separator: " + ")
    }

    func isSatisfied(by flags: CGEventFlags) -> Bool {
        if contains(.control), !flags.contains(.maskControl) {
            return false
        }

        if contains(.option), !flags.contains(.maskAlternate) {
            return false
        }

        if contains(.shift), !flags.contains(.maskShift) {
            return false
        }

        if contains(.command), !flags.contains(.maskCommand) {
            return false
        }

        return true
    }

    func isSatisfied(by flags: NSEvent.ModifierFlags) -> Bool {
        if contains(.control), !flags.contains(.control) {
            return false
        }

        if contains(.option), !flags.contains(.option) {
            return false
        }

        if contains(.shift), !flags.contains(.shift) {
            return false
        }

        if contains(.command), !flags.contains(.command) {
            return false
        }

        return true
    }

    private var displayNameComponents: [String] {
        var components: [String] = []

        if contains(.control) {
            components.append("Control")
        }

        if contains(.option) {
            components.append("Option")
        }

        if contains(.shift) {
            components.append("Shift")
        }

        if contains(.command) {
            components.append("Command")
        }

        return components
    }
}

struct HotkeyShortcut: Equatable, Sendable {
    static let defaultShortcut = HotkeyShortcut(
        keyCode: 49,
        modifiers: .option,
        keyDisplayName: "Space"
    )!
    static let escapeKeyCode: Int64 = 53

    let keyCode: Int64
    let modifiers: HotkeyModifiers
    let keyDisplayName: String

    init?(keyCode: Int64, modifiers: HotkeyModifiers, keyDisplayName: String? = nil) {
        guard !modifiers.isEmpty,
              !Self.isReservedPrimaryKey(keyCode),
              !Self.isModifierKey(keyCode) else {
            return nil
        }

        self.keyCode = keyCode
        self.modifiers = modifiers
        self.keyDisplayName = Self.defaultKeyDisplayName(
            for: keyCode,
            fallbackKeyDisplayName: keyDisplayName
        )
    }

    init?(event: NSEvent) {
        let keyCode = Int64(event.keyCode)
        let modifiers = HotkeyModifiers(eventModifierFlags: event.modifierFlags)

        self.init(
            keyCode: keyCode,
            modifiers: modifiers,
            keyDisplayName: event.charactersIgnoringModifiers
        )
    }

    var displayName: String {
        "\(modifiers.displayName) + \(keyDisplayName)"
    }

    func matches(keyCode: Int64, flags: CGEventFlags) -> Bool {
        self.keyCode == keyCode && modifiers.isSatisfied(by: flags)
    }

    func hasRequiredModifiers(_ flags: CGEventFlags) -> Bool {
        modifiers.isSatisfied(by: flags)
    }

    func hasRequiredModifiers(_ flags: NSEvent.ModifierFlags) -> Bool {
        modifiers.isSatisfied(by: flags)
    }

    private static func normalizedKeyDisplayName(_ value: String?) -> String? {
        guard let value else {
            return nil
        }

        if value == " " {
            return "Space"
        }

        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return nil
        }

        if trimmed.count == 1 {
            return trimmed.uppercased()
        }

        return trimmed
    }

    private static func defaultKeyDisplayName(
        for keyCode: Int64,
        fallbackKeyDisplayName: String? = nil
    ) -> String {
        if let keyDisplayName = keyDisplayNames[keyCode] {
            return keyDisplayName
        }

        return normalizedKeyDisplayName(fallbackKeyDisplayName) ?? "Key \(keyCode)"
    }

    private static func isReservedPrimaryKey(_ keyCode: Int64) -> Bool {
        keyCode == escapeKeyCode
    }

    private static func isModifierKey(_ keyCode: Int64) -> Bool {
        modifierKeyCodes.contains(keyCode)
    }

    private static let modifierKeyCodes: Set<Int64> = [
        54, 55, 56, 57, 58, 59, 60, 61, 62, 63
    ]

    private static let keyDisplayNames: [Int64: String] = [
        0: "A",
        1: "S",
        2: "D",
        3: "F",
        4: "H",
        5: "G",
        6: "Z",
        7: "X",
        8: "C",
        9: "V",
        11: "B",
        12: "Q",
        13: "W",
        14: "E",
        15: "R",
        16: "Y",
        17: "T",
        18: "1",
        19: "2",
        20: "3",
        21: "4",
        22: "6",
        23: "5",
        24: "=",
        25: "9",
        26: "7",
        27: "-",
        28: "8",
        29: "0",
        30: "]",
        31: "O",
        32: "U",
        33: "[",
        34: "I",
        35: "P",
        36: "Return",
        37: "L",
        38: "J",
        39: "'",
        40: "K",
        41: ";",
        42: "\\",
        43: ",",
        44: "/",
        45: "N",
        46: "M",
        47: ".",
        48: "Tab",
        49: "Space",
        50: "`",
        51: "Delete",
        65: ".",
        67: "*",
        69: "+",
        71: "Clear",
        75: "/",
        76: "Enter",
        78: "-",
        81: "=",
        82: "0",
        83: "1",
        84: "2",
        85: "3",
        86: "4",
        87: "5",
        88: "6",
        89: "7",
        91: "8",
        92: "9",
        96: "F5",
        97: "F6",
        98: "F7",
        99: "F3",
        100: "F8",
        101: "F9",
        103: "F11",
        109: "F10",
        111: "F12",
        114: "Help",
        115: "Home",
        116: "Page Up",
        117: "Forward Delete",
        118: "F4",
        119: "End",
        120: "F2",
        121: "Page Down",
        122: "F1",
        123: "Left Arrow",
        124: "Right Arrow",
        125: "Down Arrow",
        126: "Up Arrow"
    ]
}

protocol HotkeySettingsStoring {
    func load() -> HotkeyShortcut
    func save(_ shortcut: HotkeyShortcut)
}

struct UserDefaultsHotkeySettingsStore: HotkeySettingsStoring {
    private let userDefaults: UserDefaults

    init(userDefaults: UserDefaults = .standard) {
        self.userDefaults = userDefaults
    }

    func load() -> HotkeyShortcut {
        guard let keyCode = userDefaults.object(forKey: Self.keyCodeKey) as? Int,
              let modifiersRawValue = userDefaults.object(forKey: Self.modifiersKey) as? Int,
              let shortcut = HotkeyShortcut(
                keyCode: Int64(keyCode),
                modifiers: HotkeyModifiers(rawValue: modifiersRawValue),
                keyDisplayName: userDefaults.string(forKey: Self.keyDisplayNameKey)
              ) else {
            return .defaultShortcut
        }

        return shortcut
    }

    func save(_ shortcut: HotkeyShortcut) {
        userDefaults.set(Int(shortcut.keyCode), forKey: Self.keyCodeKey)
        userDefaults.set(shortcut.modifiers.rawValue, forKey: Self.modifiersKey)
        userDefaults.set(shortcut.keyDisplayName, forKey: Self.keyDisplayNameKey)
    }

    private static let keyCodeKey = "hotkey.keyCode"
    private static let modifiersKey = "hotkey.modifiers"
    private static let keyDisplayNameKey = "hotkey.keyDisplayName"
}

protocol HotkeyManaging: AnyObject {
    var onPress: (() -> Void)? { get set }
    var onRelease: (() -> Void)? { get set }
    var onCancel: (() -> Void)? { get set }
    var shortcut: HotkeyShortcut { get set }

    func restart() -> Bool
    func markSessionInactive()
}

final class HotkeyManager: HotkeyManaging {
    var onPress: (() -> Void)?
    var onRelease: (() -> Void)?
    var onCancel: (() -> Void)?
    var shortcut: HotkeyShortcut

    private var eventTap: CFMachPort?
    private var globalKeyUpMonitor: Any?
    private var globalFlagsMonitor: Any?
    private var runLoopSource: CFRunLoopSource?
    private var releaseWatchdogTimer: Timer?
    private var isHotkeyDown = false
    private var isSessionActive = false

    init(shortcut: HotkeyShortcut = UserDefaultsHotkeySettingsStore().load()) {
        self.shortcut = shortcut
    }

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
        if keyCode == HotkeyShortcut.escapeKeyCode {
            cancelHotkeySession()
            return nil
        }

        guard shortcut.matches(keyCode: keyCode, flags: event.flags) else {
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
        guard keyCode == shortcut.keyCode, isHotkeyDown else {
            return Unmanaged.passUnretained(event)
        }

        releaseHotkeySession()
        return nil
    }

    private func handleFlagsChanged(event: CGEvent) -> Unmanaged<CGEvent>? {
        guard isHotkeyDown, !shortcut.hasRequiredModifiers(event.flags) else {
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

            let modifierFlags = event.modifierFlags
            DispatchQueue.main.async {
                self.handleGlobalFlagsChanged(modifierFlags: modifierFlags)
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
        if keyCode == UInt16(HotkeyShortcut.escapeKeyCode) {
            cancelHotkeySession()
            return
        }

        guard keyCode == UInt16(shortcut.keyCode) else {
            return
        }

        releaseHotkeySession()
    }

    private func handleGlobalFlagsChanged(modifierFlags: NSEvent.ModifierFlags) {
        guard !shortcut.hasRequiredModifiers(modifierFlags) else {
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

        let isPrimaryKeyDown = CGEventSource.keyState(
            .hidSystemState,
            key: CGKeyCode(shortcut.keyCode)
        )
        let hasRequiredModifiers = shortcut.hasRequiredModifiers(
            CGEventSource.flagsState(.hidSystemState)
        )

        if !isPrimaryKeyDown || !hasRequiredModifiers {
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
