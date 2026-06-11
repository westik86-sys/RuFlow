import AVFoundation
import Foundation

@MainActor
final class DictationController: ObservableObject {
    enum State {
        case idle
        case recording
        case saving
    }

    @Published private(set) var state: State = .idle
    @Published private(set) var isAccessibilityTrusted = AccessibilityPermission.isTrusted
    @Published private(set) var microphoneAuthorizationStatus = MicrophonePermission.authorizationStatus
    @Published private(set) var hasAvailableMicrophone = MicrophonePermission.hasAvailableInput
    @Published private(set) var isHotkeyReady = false
    @Published private(set) var recordingDurationText = "00:00"
    @Published private(set) var lastErrorMessage: String?

    private let hotkeyManager = HotkeyManager()
    private let overlayController = FloatingPillWindowController()
    private let pasteService = PasteService()
    private let recordingService = AudioRecordingService()
    private var recordingTimerTask: Task<Void, Never>?
    private var errorPresentationTask: Task<Void, Never>?
    private var recordingStartedAt: Date?

    init() {
        hotkeyManager.onPress = { [weak self] in
            Task { @MainActor in
                self?.beginRecording()
            }
        }

        hotkeyManager.onRelease = { [weak self] in
            Task { @MainActor in
                self?.finishRecording()
            }
        }

        hotkeyManager.onCancel = { [weak self] in
            Task { @MainActor in
                self?.cancelRecording()
            }
        }

        refreshPermissionsAndHotkey()
        requestMicrophoneAccessIfNeeded()
    }

    var menuBarSystemImage: String {
        switch state {
        case .idle:
            "waveform.circle"
        case .recording, .saving:
            "waveform.circle.fill"
        }
    }

    var menuStatusText: String {
        if let lastErrorMessage {
            return lastErrorMessage
        }

        if !isAccessibilityTrusted {
            return "Нужен доступ Accessibility"
        }

        if !isHotkeyReady {
            return "Hotkey не запущен"
        }

        if microphoneAuthorizationStatus != .authorized {
            return "Нужен доступ к микрофону"
        }

        if !hasAvailableMicrophone {
            return "Микрофон не найден"
        }

        switch state {
        case .idle:
            return "Готово: Option + Space"
        case .recording:
            return "Слушаю... \(recordingDurationText)"
        case .saving:
            return "Сохраняю запись..."
        }
    }

    var microphoneStatusText: String {
        if !hasAvailableMicrophone {
            return "Микрофон не найден"
        }

        return MicrophonePermission.statusText(for: microphoneAuthorizationStatus)
    }

    var recordingsDirectoryPath: String {
        recordingService.recordingsDirectory?.path ?? "Application Support/RuFlow/Recordings"
    }

    func refreshPermissionsAndHotkey() {
        isAccessibilityTrusted = AccessibilityPermission.isTrusted
        microphoneAuthorizationStatus = MicrophonePermission.authorizationStatus
        hasAvailableMicrophone = MicrophonePermission.hasAvailableInput
        isHotkeyReady = hotkeyManager.restart()
    }

    func requestMicrophoneAccessIfNeeded() {
        Task { @MainActor [weak self] in
            _ = await MicrophonePermission.requestIfNeeded()
            self?.refreshPermissionsAndHotkey()
        }
    }

    private func beginRecording() {
        clearError()
        recordingService.cancelRecording()
        stopRecordingTimer()
        refreshPermissionsAndHotkey()

        guard microphoneAuthorizationStatus == .authorized else {
            requestMicrophoneAccessIfNeeded()
            presentError("Нет разрешения на микрофон")
            hotkeyManager.markSessionInactive()
            return
        }

        do {
            try recordingService.startRecording()
            state = .recording
            startRecordingTimer()
        } catch {
            presentError(error.localizedDescription)
            recordingService.cancelRecording()
            hotkeyManager.markSessionInactive()
        }
    }

    private func finishRecording() {
        guard state == .recording else {
            return
        }

        stopRecordingTimer()
        state = .saving
        overlayController.show(message: "Сохраняю запись...")

        do {
            let outputURL = try recordingService.stopRecording()
            pasteService.insertText(outputURL.path) { [weak self] in
                self?.completeRecording()
            }
        } catch {
            recordingService.cancelRecording()
            presentError(error.localizedDescription)
            hotkeyManager.markSessionInactive()
        }
    }

    private func cancelRecording() {
        stopRecordingTimer()
        recordingService.cancelRecording()
        state = .idle
        overlayController.hide()
        hotkeyManager.markSessionInactive()
    }

    private func completeRecording() {
        stopRecordingTimer()
        state = .idle
        overlayController.hide()
        hotkeyManager.markSessionInactive()
    }

    private func startRecordingTimer() {
        recordingStartedAt = Date()
        updateRecordingTimer()

        recordingTimerTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                self?.updateRecordingTimer()

                do {
                    try await Task.sleep(for: .milliseconds(200))
                } catch {
                    return
                }
            }
        }
    }

    private func stopRecordingTimer() {
        recordingTimerTask?.cancel()
        recordingTimerTask = nil
        recordingStartedAt = nil
        recordingDurationText = "00:00"
    }

    private func updateRecordingTimer() {
        guard let recordingStartedAt else {
            recordingDurationText = "00:00"
            overlayController.show(message: "Слушаю... 00:00")
            return
        }

        let elapsedSeconds = max(0, Int(Date().timeIntervalSince(recordingStartedAt)))
        let minutes = elapsedSeconds / 60
        let seconds = elapsedSeconds % 60
        recordingDurationText = String(format: "%02d:%02d", minutes, seconds)
        overlayController.show(message: "Слушаю... \(recordingDurationText)")
    }

    private func presentError(_ message: String) {
        state = .idle
        lastErrorMessage = message
        overlayController.show(message: message)

        errorPresentationTask?.cancel()
        errorPresentationTask = Task { @MainActor [weak self] in
            do {
                try await Task.sleep(for: .seconds(2))
            } catch {
                return
            }

            guard self?.lastErrorMessage == message else {
                return
            }

            self?.lastErrorMessage = nil
            self?.overlayController.hide()
        }
    }

    private func clearError() {
        errorPresentationTask?.cancel()
        errorPresentationTask = nil
        lastErrorMessage = nil
    }
}
