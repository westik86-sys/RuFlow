import AVFoundation
import Foundation

@MainActor
final class DictationController: ObservableObject {
    enum State: Equatable {
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

    private let maximumRecordingDuration: TimeInterval = 25
    private let hotkeyManager = HotkeyManager()
    private let overlayController = FloatingPillWindowController()
    private let pasteService = PasteService()
    private let recordingService = AudioRecordingService()
    private let asrService = ASRSidecarService()
    private let asrConfiguration = ASRDebugConfiguration.current
    private var recordingTimerTask: Task<Void, Never>?
    private var errorPresentationTask: Task<Void, Never>?
    private var asrTask: Task<Void, Never>?
    private var recordingStartedAt: Date?
    private var completedRecordingURL: URL?
    private var lastDisplayedRemainingSeconds: Int?

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
            return "Слушаю... осталось \(recordingDurationText)"
        case .saving:
            return "Распознаю..."
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

    var asrPythonPath: String {
        asrConfiguration.pythonPathForDisplay
    }

    var asrRunnerPath: String {
        asrConfiguration.runnerPathForDisplay
    }

    var runningAppPath: String {
        Bundle.main.bundleURL.path
    }

    var accessibilityStatusText: String {
        isAccessibilityTrusted ? "Разрешено" : "Требуется для этой копии приложения"
    }

    var isMicrophoneAuthorized: Bool {
        microphoneAuthorizationStatus == .authorized
    }

    var canRequestMicrophonePermission: Bool {
        microphoneAuthorizationStatus == .notDetermined
    }

    var isMicrophonePermissionDenied: Bool {
        microphoneAuthorizationStatus == .denied
    }

    var needsPermissionPolling: Bool {
        !isAccessibilityTrusted || !isMicrophoneAuthorized
    }

    var isRecordingOrSaving: Bool {
        state == .recording || state == .saving
    }

    func refreshPermissionsAndHotkey() {
        refreshPermissionState()
        isHotkeyReady = hotkeyManager.restart()
    }

    func refreshPermissionStatus() {
        let wasAccessibilityTrusted = isAccessibilityTrusted
        refreshPermissionState()

        if wasAccessibilityTrusted != isAccessibilityTrusted {
            isHotkeyReady = hotkeyManager.restart()
        }
    }

    func requestMicrophoneAccessIfNeeded() {
        Task { @MainActor [weak self] in
            _ = await MicrophonePermission.requestIfNeeded()
            self?.refreshPermissionStatus()
        }
    }

    func stopRecordingFromMenu() {
        stopRecordingFromUserAction()
    }

    func stopRecordingFromUserAction() {
        finishRecording()
        hotkeyManager.markSessionInactive()
    }

    func cancelRecordingFromMenu() {
        cancelRecording()
    }

    private func beginRecording() {
        guard state == .idle else {
            return
        }

        clearError()
        recordingService.cancelRecording()
        stopRecordingTimer()
        completedRecordingURL = nil
        refreshPermissionState()

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

        overlayController.showLoader()
        stopRecordingTimer()
        state = .saving

        do {
            let outputURL = try recordingService.stopRecording()
            completedRecordingURL = outputURL
            asrTask?.cancel()
            asrTask = Task { [weak self] in
                await self?.transcribeAndInsert(audioURL: outputURL)
            }
        } catch {
            recordingService.cancelRecording()
            presentError(error.localizedDescription)
            hotkeyManager.markSessionInactive()
        }
    }

    private func cancelRecording() {
        stopRecordingTimer()
        asrTask?.cancel()
        asrTask = nil
        recordingService.cancelRecording()

        if let completedRecordingURL {
            try? FileManager.default.removeItem(at: completedRecordingURL)
        }

        completedRecordingURL = nil
        state = .idle
        overlayController.hide()
        hotkeyManager.markSessionInactive()
    }

    private func completeRecording(audioURL: URL) {
        guard state == .saving, completedRecordingURL == audioURL else {
            return
        }

        stopRecordingTimer()
        asrTask = nil
        try? FileManager.default.removeItem(at: audioURL)
        completedRecordingURL = nil
        state = .idle
        overlayController.hide()
        hotkeyManager.markSessionInactive()
    }

    private func transcribeAndInsert(audioURL: URL) async {
        do {
            let result = try await asrService.transcribe(
                audioURL: audioURL,
                configuration: asrConfiguration
            )

            guard !Task.isCancelled, state == .saving, completedRecordingURL == audioURL else {
                return
            }

            let text = result.text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else {
                throw ASRSidecarError.emptyText
            }

            pasteService.insertText(text) { [weak self] in
                self?.completeRecording(audioURL: audioURL)
            }
        } catch {
            guard !Task.isCancelled else {
                return
            }

            handleASRFailure(error, audioURL: audioURL)
        }
    }

    private func handleASRFailure(_ error: Error, audioURL: URL) {
        pasteService.copyTextToClipboard(audioURL.path)
        asrTask = nil
        completedRecordingURL = nil
        presentError(error.localizedDescription)
        hotkeyManager.markSessionInactive()
    }

    private func startRecordingTimer() {
        recordingStartedAt = Date()
        lastDisplayedRemainingSeconds = nil
        updateRecordingTimer()

        recordingTimerTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                self?.updateRecordingTimer()

                do {
                    try await Task.sleep(for: .milliseconds(60))
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
        lastDisplayedRemainingSeconds = nil
        recordingDurationText = "00:00"
    }

    private func updateRecordingTimer() {
        guard let recordingStartedAt else {
            recordingDurationText = formattedDuration(Int(maximumRecordingDuration))
            return
        }

        let elapsed = Date().timeIntervalSince(recordingStartedAt)
        let remainingSeconds = max(0, Int(ceil(maximumRecordingDuration - elapsed)))

        if lastDisplayedRemainingSeconds != remainingSeconds {
            recordingDurationText = formattedDuration(remainingSeconds)
            lastDisplayedRemainingSeconds = remainingSeconds
        }

        overlayController.showRecording(
            message: compactFormattedDuration(remainingSeconds),
            level: recordingService.normalizedMeterLevel(),
            onStop: { [weak self] in
                self?.stopRecordingFromUserAction()
            },
            onCancel: { [weak self] in
                self?.cancelRecording()
            }
        )

        if elapsed >= maximumRecordingDuration {
            finishRecording()
        }
    }

    private func formattedDuration(_ totalSeconds: Int) -> String {
        let minutes = totalSeconds / 60
        let seconds = totalSeconds % 60
        return String(format: "%02d:%02d", minutes, seconds)
    }

    private func compactFormattedDuration(_ totalSeconds: Int) -> String {
        let minutes = totalSeconds / 60
        let seconds = totalSeconds % 60
        return String(format: "%d:%02d", minutes, seconds)
    }

    private func refreshPermissionState() {
        isAccessibilityTrusted = AccessibilityPermission.isTrusted
        microphoneAuthorizationStatus = MicrophonePermission.authorizationStatus
        hasAvailableMicrophone = MicrophonePermission.hasAvailableInput
    }

    private func presentError(_ message: String) {
        state = .idle
        lastErrorMessage = message
        overlayController.showError(message: message)

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
