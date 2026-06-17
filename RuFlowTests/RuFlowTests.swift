import AVFoundation
import Darwin
import XCTest
@testable import RuFlow

final class ASRSidecarResponseParserTests: XCTestCase {
    func testParsesSuccessJSON() throws {
        let result = try parse("""
        {"ok":true,"text":"  Привет  ","duration_ms":123,"model":"gigaam-v3-e2e-rnnt"}
        """)

        XCTAssertEqual(result.text, "Привет")
        XCTAssertEqual(result.durationMs, 123)
        XCTAssertEqual(result.model, "gigaam-v3-e2e-rnnt")
    }

    func testThrowsFailedWhenOkIsFalse() {
        assertFailed(
            try parse("""
            {"ok":false,"error":"model returned empty transcript","duration_ms":12,"model":"gigaam-v3-e2e-rnnt"}
            """),
            status: 0,
            message: "model returned empty transcript"
        )
    }

    func testThrowsInvalidJSON() {
        XCTAssertThrowsError(try parse("not json")) { error in
            guard case ASRSidecarError.invalidJSON(let message) = error else {
                XCTFail("Expected invalidJSON, got \(error)")
                return
            }

            XCTAssertFalse(message.isEmpty)
        }
    }

    func testThrowsEmptyText() {
        XCTAssertThrowsError(
            try parse("""
            {"ok":true,"text":"  ","duration_ms":12,"model":"gigaam-v3-e2e-rnnt"}
            """)
        ) { error in
            guard case ASRSidecarError.emptyText = error else {
                XCTFail("Expected emptyText, got \(error)")
                return
            }
        }
    }

    func testThrowsFailedWhenModelMismatches() {
        assertFailed(
            try parse("""
            {"ok":true,"text":"Привет","duration_ms":12,"model":"other-model"}
            """),
            status: 0,
            message: "неожиданная модель: other-model"
        )
    }

    func testThrowsFailedForNonzeroExitWithStderr() {
        assertFailed(
            try ASRSidecarResponseParser.parse(
                stdoutData: Data(),
                stderrText: "sidecar crashed\n",
                terminationStatus: 2
            ),
            status: 2,
            message: "sidecar crashed"
        )
    }

    private func parse(
        _ stdout: String,
        stderr: String = "",
        terminationStatus: Int32 = 0
    ) throws -> ASRSidecarResult {
        try ASRSidecarResponseParser.parse(
            stdoutData: Data(stdout.utf8),
            stderrText: stderr,
            terminationStatus: terminationStatus
        )
    }

    private func assertFailed(
        _ expression: @autoclosure () throws -> ASRSidecarResult,
        status: Int32,
        message: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        XCTAssertThrowsError(try expression(), file: file, line: line) { error in
            guard case ASRSidecarError.failed(let actualStatus, let actualMessage) = error else {
                XCTFail("Expected failed, got \(error)", file: file, line: line)
                return
            }

            XCTAssertEqual(actualStatus, status, file: file, line: line)
            XCTAssertEqual(actualMessage, message, file: file, line: line)
        }
    }
}

final class DictationTextFormatterTests: XCTestCase {
    func testRemovesFinalPeriodFromSingleSentence() {
        XCTAssertEqual(
            DictationTextFormatter.formatForInsertion("  Привет это тест.  "),
            "Привет это тест"
        )
    }

    func testKeepsFinalPeriodForMultipleSentences() {
        XCTAssertEqual(
            DictationTextFormatter.formatForInsertion("Привет. Это тест."),
            "Привет. Это тест."
        )
    }

    func testKeepsQuestionAndExclamationMarksForSingleSentence() {
        XCTAssertEqual(DictationTextFormatter.formatForInsertion("Как дела?"), "Как дела?")
        XCTAssertEqual(DictationTextFormatter.formatForInsertion("Отлично!"), "Отлично!")
    }

    func testKeepsEllipsisForSingleSentence() {
        XCTAssertEqual(DictationTextFormatter.formatForInsertion("Ну вот..."), "Ну вот...")
    }
}

final class HotkeyShortcutTests: XCTestCase {
    func testDefaultShortcutUsesOptionSpace() {
        XCTAssertEqual(HotkeyShortcut.defaultShortcut.keyCode, 49)
        XCTAssertEqual(HotkeyShortcut.defaultShortcut.modifiers, .option)
        XCTAssertEqual(HotkeyShortcut.defaultShortcut.displayName, "Option + Space")
    }

    func testRejectsShortcutWithoutModifiers() {
        XCTAssertNil(HotkeyShortcut(keyCode: 49, modifiers: [], keyDisplayName: "Space"))
    }

    func testRejectsEscapeShortcutBecauseItCancelsRecording() {
        XCTAssertNil(
            HotkeyShortcut(
                keyCode: HotkeyShortcut.escapeKeyCode,
                modifiers: .option,
                keyDisplayName: "Escape"
            )
        )
    }

    func testUsesLatinPhysicalKeyNameForCyrillicInputLayout() throws {
        let shortcut = try XCTUnwrap(
            HotkeyShortcut(keyCode: 40, modifiers: .shift, keyDisplayName: "л")
        )

        XCTAssertEqual(shortcut.displayName, "Shift + K")
    }

    func testUsesPhysicalNumberKeyNameForShiftSymbol() throws {
        let shortcut = try XCTUnwrap(
            HotkeyShortcut(keyCode: 21, modifiers: .shift, keyDisplayName: "$")
        )

        XCTAssertEqual(shortcut.displayName, "Shift + 4")
    }

    func testMatchesPrimaryKeyWithRequiredModifiers() throws {
        let shortcut = try XCTUnwrap(
            HotkeyShortcut(keyCode: 40, modifiers: [.control, .option], keyDisplayName: "K")
        )

        XCTAssertTrue(shortcut.matches(keyCode: 40, flags: [.maskControl, .maskAlternate]))
        XCTAssertFalse(shortcut.matches(keyCode: 40, flags: .maskControl))
        XCTAssertFalse(shortcut.matches(keyCode: 41, flags: [.maskControl, .maskAlternate]))
    }

    func testUserDefaultsStoreRoundTripsShortcut() throws {
        let suiteName = "RuFlowHotkeyShortcutTests-\(UUID().uuidString)"
        let userDefaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer {
            userDefaults.removePersistentDomain(forName: suiteName)
        }

        let store = UserDefaultsHotkeySettingsStore(userDefaults: userDefaults)
        let shortcut = try XCTUnwrap(
            HotkeyShortcut(keyCode: 40, modifiers: [.control, .option], keyDisplayName: "K")
        )

        store.save(shortcut)

        XCTAssertEqual(store.load(), shortcut)
    }
}

@MainActor
final class DictationControllerHotkeyTests: XCTestCase {
    func testUpdatesHotkeyShortcutAndRestartsHotkeyManager() throws {
        let events = TestEventLog()
        let hotkey = FakeHotkeyManager()
        let store = FakeHotkeySettingsStore(shortcut: .defaultShortcut)
        let controller = DictationController(
            hotkeyManager: hotkey,
            overlayController: FakeDictationOverlayPresenter(events: events),
            recordingService: FakeAudioRecordingService(events: events),
            microphonePermission: FakeMicrophonePermissionProvider(
                authorizationStatus: .authorized,
                hasAvailableInput: true
            ),
            hotkeySettingsStore: store,
            requestMicrophoneAccessOnInit: false
        )
        let restartCallCount = hotkey.restartCallCount
        let shortcut = try XCTUnwrap(
            HotkeyShortcut(keyCode: 40, modifiers: [.control, .option], keyDisplayName: "K")
        )

        controller.updateHotkeyShortcut(shortcut)

        XCTAssertEqual(controller.hotkeyShortcut, shortcut)
        XCTAssertEqual(controller.hotkeyShortcutText, "Control + Option + K")
        XCTAssertEqual(hotkey.shortcut, shortcut)
        XCTAssertEqual(store.savedShortcut, shortcut)
        XCTAssertEqual(hotkey.restartCallCount, restartCallCount + 1)
    }
}

final class LoginLaunchAgentServiceTests: XCTestCase {
    func testLaunchAgentOpensRuFlowByBundleIdentifier() {
        let plist = LoginLaunchAgentService.propertyList()

        XCTAssertEqual(plist["Label"] as? String, "com.ruflow.RuFlow.login")
        XCTAssertEqual(plist["RunAtLoad"] as? Bool, true)
        XCTAssertEqual(plist["LimitLoadToSessionType"] as? String, "Aqua")
        XCTAssertEqual(
            plist["ProgramArguments"] as? [String],
            ["/usr/bin/open", "-b", "com.ruflow.RuFlow"]
        )
    }

    func testLaunchAgentPlistDataIsValidXMLPropertyList() throws {
        let data = try LoginLaunchAgentService.plistData()
        let plist = try PropertyListSerialization.propertyList(
            from: data,
            options: [],
            format: nil
        )

        guard let dictionary = plist as? [String: Any] else {
            XCTFail("Expected dictionary plist")
            return
        }

        XCTAssertEqual(dictionary["Label"] as? String, "com.ruflow.RuFlow.login")
        XCTAssertEqual(
            dictionary["ProgramArguments"] as? [String],
            ["/usr/bin/open", "-b", "com.ruflow.RuFlow"]
        )
    }
}

final class RuFlowChangelogTests: XCTestCase {
    func testLatestEntryUsesCurrentReleaseVersion() throws {
        let latestEntry = try XCTUnwrap(RuFlowChangelog.entries.first)

        XCTAssertEqual(RuFlowChangelog.latestVersion, "1.0")
        XCTAssertEqual(latestEntry.version, "1.0")
        XCTAssertEqual(latestEntry.dateText, "16 июня 2026")
    }

    func testLatestEntryUsesUserFacingSections() throws {
        let latestEntry = try XCTUnwrap(RuFlowChangelog.entries.first)

        XCTAssertEqual(
            latestEntry.sections.map(\.title),
            ["Добавлено", "Улучшено", "Исправлено"]
        )
        XCTAssertTrue(latestEntry.sections.allSatisfy { !$0.items.isEmpty })
    }

    func testChangelogItemsAreUserFacingAndNonEmpty() {
        let items = RuFlowChangelog.entries
            .flatMap(\.sections)
            .flatMap(\.items)
            .map(\.text)

        XCTAssertEqual(items.count, 6)
        XCTAssertTrue(items.allSatisfy { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty })
    }
}

final class ASRSidecarServiceTests: XCTestCase {
    func testTranscribeUsesProcessRunnerAndParsesOutput() async throws {
        let audioURL = try makeTemporaryFile(extension: "wav")
        let runnerURL = try makeTemporaryFile(extension: "py")
        defer {
            try? FileManager.default.removeItem(at: audioURL)
            try? FileManager.default.removeItem(at: runnerURL)
        }

        let fakeRunner = FakeASRSidecarProcessRunner(
            output: ASRSidecarProcessOutput(
                stdoutData: Data("""
                {"ok":true,"text":"Привет","duration_ms":42,"model":"gigaam-v3-e2e-rnnt"}
                """.utf8),
                stderrText: "",
                terminationStatus: 0
            )
        )
        let service = ASRSidecarService(processRunner: fakeRunner)

        let result = try await service.transcribe(
            audioURL: audioURL,
            configuration: ASRDebugConfiguration(
                pythonPath: "/bin/sh",
                runnerPath: runnerURL.path,
                sidecarExecutablePath: "",
                modelDirectoryPath: ""
            )
        )

        XCTAssertEqual(result.text, "Привет")
        XCTAssertEqual(result.durationMs, 42)

        let request = try XCTUnwrap(fakeRunner.recordedRequests.first)
        XCTAssertEqual(request.executableURL.path, "/bin/sh")
        XCTAssertEqual(request.arguments, [runnerURL.path, audioURL.path])
        XCTAssertEqual(request.currentDirectoryURL, runnerURL.deletingLastPathComponent())
        XCTAssertNil(request.environment)
    }

    func testTranscribePropagatesCancellationToProcessRunner() async throws {
        let audioURL = try makeTemporaryFile(extension: "wav")
        let runnerURL = try makeTemporaryFile(extension: "py")
        defer {
            try? FileManager.default.removeItem(at: audioURL)
            try? FileManager.default.removeItem(at: runnerURL)
        }

        let started = expectation(description: "runner started")
        let cancelled = expectation(description: "runner cancelled")
        let fakeRunner = FakeASRSidecarProcessRunner { _ in
            started.fulfill()

            do {
                try await Task.sleep(nanoseconds: 10_000_000_000)
                return ASRSidecarProcessOutput(stdoutData: Data(), stderrText: "", terminationStatus: 0)
            } catch {
                cancelled.fulfill()
                throw error
            }
        }
        let service = ASRSidecarService(processRunner: fakeRunner)

        let task = Task {
            try await service.transcribe(
                audioURL: audioURL,
                configuration: ASRDebugConfiguration(
                    pythonPath: "/bin/sh",
                    runnerPath: runnerURL.path,
                    sidecarExecutablePath: "",
                    modelDirectoryPath: ""
                )
            )
        }

        await fulfillment(of: [started], timeout: 1)
        task.cancel()

        do {
            _ = try await task.value
            XCTFail("Expected cancellation")
        } catch is CancellationError {
            // Expected.
        }

        await fulfillment(of: [cancelled], timeout: 1)
    }

    func testProcessRunnerDrainsLargeStderrWithoutDeadlock() async throws {
        let directoryURL = try makeTemporaryDirectory()
        defer {
            try? FileManager.default.removeItem(at: directoryURL)
        }

        let scriptURL = try makeShellScript(
            in: directoryURL,
            contents: """
            yes x | head -c 1200000 >&2
            printf '{"ok":true,"text":"done","duration_ms":7,"model":"gigaam-v3-e2e-rnnt"}'
            """
        )
        let runner = ASRSidecarProcessRunner()

        let output = try await withTimeout(seconds: 5) {
            try await runner.run(
                ASRSidecarProcessRequest(
                    executableURL: URL(fileURLWithPath: "/bin/sh"),
                    arguments: [scriptURL.path],
                    currentDirectoryURL: directoryURL,
                    environment: nil
                )
            )
        }

        XCTAssertEqual(output.terminationStatus, 0)
        XCTAssertGreaterThan(output.stderrText.utf8.count, 1_000_000)

        let result = try ASRSidecarResponseParser.parse(
            stdoutData: output.stdoutData,
            stderrText: output.stderrText,
            terminationStatus: output.terminationStatus
        )
        XCTAssertEqual(result.text, "done")
        XCTAssertEqual(result.durationMs, 7)
    }

    func testProcessRunnerCancellationTerminatesChildProcess() async throws {
        let directoryURL = try makeTemporaryDirectory()
        defer {
            try? FileManager.default.removeItem(at: directoryURL)
        }

        let pidFileURL = directoryURL.appendingPathComponent("child.pid")
        let scriptURL = try makeShellScript(
            in: directoryURL,
            contents: """
            printf "%s\\n" "$$" > "$1"
            while :; do
                sleep 1
            done
            """
        )
        let runner = ASRSidecarProcessRunner()
        let task = Task {
            try await runner.run(
                ASRSidecarProcessRequest(
                    executableURL: URL(fileURLWithPath: "/bin/sh"),
                    arguments: [scriptURL.path, pidFileURL.path],
                    currentDirectoryURL: directoryURL,
                    environment: nil
                )
            )
        }

        let pid = try await waitForPID(at: pidFileURL, timeoutSeconds: 2)
        task.cancel()

        do {
            _ = try await withTimeout(seconds: 5) {
                try await task.value
            }
            XCTFail("Expected cancellation")
        } catch is CancellationError {
            // Expected.
        }

        try await waitUntilProcessExits(pid: pid, timeoutSeconds: 2)
    }

    private func makeTemporaryFile(extension fileExtension: String) throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension(fileExtension)
        try Data().write(to: url)
        return url
    }

    private func makeTemporaryDirectory() throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    private func makeShellScript(in directoryURL: URL, contents: String) throws -> URL {
        let scriptURL = directoryURL.appendingPathComponent("script.sh")
        let script = "#!/bin/sh\n" + contents + "\n"
        try script.write(to: scriptURL, atomically: true, encoding: .utf8)
        return scriptURL
    }

    private func waitForPID(at url: URL, timeoutSeconds: UInt64) async throws -> pid_t {
        try await withTimeout(seconds: timeoutSeconds) {
            while true {
                if let text = try? String(contentsOf: url, encoding: .utf8),
                   let pid = Int32(text.trimmingCharacters(in: .whitespacesAndNewlines)) {
                    return pid
                }

                try await Task.sleep(nanoseconds: 50_000_000)
            }
        }
    }

    private func waitUntilProcessExits(pid: pid_t, timeoutSeconds: UInt64) async throws {
        try await withTimeout(seconds: timeoutSeconds) {
            while isProcessAlive(pid) {
                try await Task.sleep(nanoseconds: 50_000_000)
            }
        }
    }
}

final class AudioRecordingServiceTests: XCTestCase {
    func testRemoveRecordingDeletesTemporaryAudioFile() throws {
        let audioURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("wav")
        try Data("audio".utf8).write(to: audioURL)

        AudioRecordingService().removeRecording(at: audioURL)

        XCTAssertFalse(FileManager.default.fileExists(atPath: audioURL.path))
    }

    func testRemoveRecordingIgnoresMissingFile() throws {
        let audioURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("wav")

        AudioRecordingService().removeRecording(at: audioURL)

        XCTAssertFalse(FileManager.default.fileExists(atPath: audioURL.path))
    }
}

@MainActor
final class DictationControllerOverlayFailSafeTests: XCTestCase {
    func testStartsRecordingOnlyAfterOverlayIsVisible() async {
        let environment = makeController()

        environment.hotkey.press()
        await Task.yield()

        XCTAssertEqual(environment.controller.state, .recording)
        XCTAssertTrue(environment.recorder.isRecording)

        let showIndex = environment.events.values.firstIndex(of: "overlay.showRecording")
        let startIndex = environment.events.values.firstIndex(of: "recorder.startRecording")
        XCTAssertNotNil(showIndex)
        XCTAssertNotNil(startIndex)

        if let showIndex, let startIndex {
            XCTAssertLessThan(showIndex, startIndex)
        }

        environment.controller.cancelRecordingFromMenu()
    }

    func testDoesNotStartRecordingWhenOverlayThrows() async {
        let environment = makeController()
        environment.overlay.showRecordingError = TestDictationError.overlayFailed

        environment.hotkey.press()
        await Task.yield()

        XCTAssertEqual(environment.controller.state, .idle)
        XCTAssertEqual(environment.recorder.startRecordingCallCount, 0)
        XCTAssertFalse(environment.recorder.isRecording)
        XCTAssertGreaterThanOrEqual(environment.recorder.cancelRecordingCallCount, 1)
        XCTAssertEqual(environment.hotkey.markSessionInactiveCallCount, 1)
        XCTAssertEqual(environment.overlay.hideCallCount, 1)
        XCTAssertEqual(environment.overlay.showErrorCallCount, 1)
        XCTAssertEqual(environment.controller.lastErrorMessage, TestDictationError.overlayFailed.localizedDescription)
    }

    func testDoesNotStartRecordingWhenOverlayIsNotVisible() async {
        let environment = makeController()
        environment.overlay.showRecordingResult = false
        environment.overlay.isVisibleOnScreen = false

        environment.hotkey.press()
        await Task.yield()

        XCTAssertEqual(environment.controller.state, .idle)
        XCTAssertEqual(environment.recorder.startRecordingCallCount, 0)
        XCTAssertFalse(environment.recorder.isRecording)
        XCTAssertGreaterThanOrEqual(environment.recorder.cancelRecordingCallCount, 1)
        XCTAssertEqual(environment.hotkey.markSessionInactiveCallCount, 1)
        XCTAssertEqual(environment.overlay.showErrorCallCount, 1)
        XCTAssertEqual(environment.controller.lastErrorMessage, FloatingPillPresentationError.notVisible.localizedDescription)
    }

    func testCancelsRecordingWhenOverlayDisappearsDuringRecording() async throws {
        let environment = makeController()
        environment.hotkey.press()
        await Task.yield()
        XCTAssertEqual(environment.controller.state, .recording)
        XCTAssertTrue(environment.recorder.isRecording)

        environment.overlay.isVisibleOnScreen = false
        try await Task.sleep(nanoseconds: 150_000_000)

        XCTAssertEqual(environment.controller.state, .idle)
        XCTAssertFalse(environment.recorder.isRecording)
        XCTAssertGreaterThanOrEqual(environment.recorder.cancelRecordingCallCount, 1)
        XCTAssertEqual(environment.hotkey.markSessionInactiveCallCount, 1)
        XCTAssertEqual(environment.overlay.showErrorCallCount, 1)
    }

    private func makeController() -> (
        controller: DictationController,
        hotkey: FakeHotkeyManager,
        overlay: FakeDictationOverlayPresenter,
        recorder: FakeAudioRecordingService,
        events: TestEventLog
    ) {
        let events = TestEventLog()
        let hotkey = FakeHotkeyManager()
        let overlay = FakeDictationOverlayPresenter(events: events)
        let recorder = FakeAudioRecordingService(events: events)
        let microphonePermission = FakeMicrophonePermissionProvider(
            authorizationStatus: .authorized,
            hasAvailableInput: true
        )
        let controller = DictationController(
            hotkeyManager: hotkey,
            overlayController: overlay,
            recordingService: recorder,
            microphonePermission: microphonePermission,
            hotkeySettingsStore: FakeHotkeySettingsStore(shortcut: .defaultShortcut),
            requestMicrophoneAccessOnInit: false
        )

        return (controller, hotkey, overlay, recorder, events)
    }
}

private enum TestTimeoutError: Error {
    case timedOut
}

private enum TestDictationError: LocalizedError {
    case overlayFailed

    var errorDescription: String? {
        switch self {
        case .overlayFailed:
            return "overlay failed"
        }
    }
}

private final class TestEventLog {
    private(set) var values: [String] = []

    func append(_ value: String) {
        values.append(value)
    }
}

private final class FakeHotkeyManager: HotkeyManaging {
    var onPress: (() -> Void)?
    var onRelease: (() -> Void)?
    var onCancel: (() -> Void)?
    var shortcut: HotkeyShortcut = .defaultShortcut
    private(set) var restartCallCount = 0
    private(set) var markSessionInactiveCallCount = 0

    func restart() -> Bool {
        restartCallCount += 1
        return true
    }

    func markSessionInactive() {
        markSessionInactiveCallCount += 1
    }

    func press() {
        onPress?()
    }
}

private final class FakeHotkeySettingsStore: HotkeySettingsStoring {
    private let shortcut: HotkeyShortcut
    private(set) var savedShortcut: HotkeyShortcut?

    init(shortcut: HotkeyShortcut) {
        self.shortcut = shortcut
    }

    func load() -> HotkeyShortcut {
        shortcut
    }

    func save(_ shortcut: HotkeyShortcut) {
        savedShortcut = shortcut
    }
}

@MainActor
private final class FakeDictationOverlayPresenter: DictationOverlayPresenting {
    var isVisibleOnScreen = true
    var showRecordingResult = true
    var showRecordingError: Error?
    private(set) var showRecordingCallCount = 0
    private(set) var showLoaderCallCount = 0
    private(set) var showErrorCallCount = 0
    private(set) var hideCallCount = 0
    private let events: TestEventLog

    init(events: TestEventLog) {
        self.events = events
    }

    func showRecording(
        message: String,
        level: Double,
        onStop: @escaping () -> Void,
        onCancel: @escaping () -> Void
    ) throws -> Bool {
        showRecordingCallCount += 1
        events.append("overlay.showRecording")

        if let showRecordingError {
            throw showRecordingError
        }

        return showRecordingResult
    }

    func showLoader() {
        showLoaderCallCount += 1
    }

    func showError(message: String) {
        showErrorCallCount += 1
    }

    func hide() {
        hideCallCount += 1
        isVisibleOnScreen = false
    }
}

private final class FakeAudioRecordingService: AudioRecordingServicing {
    var recordingsDirectory: URL?
    var startRecordingError: Error?
    var stopRecordingURL = URL(fileURLWithPath: "/tmp/ruflow-test.wav")
    private(set) var startRecordingCallCount = 0
    private(set) var stopRecordingCallCount = 0
    private(set) var cancelRecordingCallCount = 0
    private(set) var removeRecordingCallCount = 0
    private(set) var isRecording = false
    private let events: TestEventLog

    init(events: TestEventLog) {
        self.events = events
    }

    func startRecording() throws {
        startRecordingCallCount += 1
        events.append("recorder.startRecording")

        if let startRecordingError {
            throw startRecordingError
        }

        isRecording = true
    }

    func normalizedMeterLevel() -> Double {
        0
    }

    func stopRecording() throws -> URL {
        stopRecordingCallCount += 1
        isRecording = false
        return stopRecordingURL
    }

    func cancelRecording() {
        cancelRecordingCallCount += 1
        isRecording = false
    }

    func removeRecording(at outputURL: URL) {
        removeRecordingCallCount += 1
    }
}

private struct FakeMicrophonePermissionProvider: MicrophonePermissionProviding {
    let authorizationStatus: AVAuthorizationStatus
    let hasAvailableInput: Bool

    func requestIfNeeded() async -> Bool {
        authorizationStatus == .authorized
    }
}

private final class TestTimeoutState<T: Sendable>: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<T, Error>?
    private var result: Result<T, Error>?

    func setContinuation(_ continuation: CheckedContinuation<T, Error>) {
        let result: Result<T, Error>?

        lock.lock()
        if let storedResult = self.result {
            result = storedResult
        } else {
            self.continuation = continuation
            result = nil
        }
        lock.unlock()

        if let result {
            resume(continuation, with: result)
        }
    }

    func complete(_ result: Result<T, Error>) {
        let continuation: CheckedContinuation<T, Error>?

        lock.lock()
        guard self.result == nil else {
            lock.unlock()
            return
        }

        self.result = result
        continuation = self.continuation
        self.continuation = nil
        lock.unlock()

        if let continuation {
            resume(continuation, with: result)
        }
    }

    private func resume(
        _ continuation: CheckedContinuation<T, Error>,
        with result: Result<T, Error>
    ) {
        switch result {
        case .success(let value):
            continuation.resume(returning: value)
        case .failure(let error):
            continuation.resume(throwing: error)
        }
    }
}

private func withTimeout<T: Sendable>(
    seconds: UInt64,
    operation: @escaping @Sendable () async throws -> T
) async throws -> T {
    let state = TestTimeoutState<T>()
    let operationTask = Task<T, Error> {
        try await operation()
    }
    let timeoutTask = Task {
        try? await Task.sleep(nanoseconds: seconds * 1_000_000_000)
        operationTask.cancel()
        state.complete(.failure(TestTimeoutError.timedOut))
    }

    let result = try await withCheckedThrowingContinuation { continuation in
        state.setContinuation(continuation)

        Task {
            do {
                let value = try await operationTask.value
                state.complete(.success(value))
            } catch {
                state.complete(.failure(error))
            }
        }
    }

    timeoutTask.cancel()
    return result
}

private func isProcessAlive(_ pid: pid_t) -> Bool {
    if Darwin.kill(pid, 0) == 0 {
        return true
    }

    return errno != ESRCH
}

private final class FakeASRSidecarProcessRunner: ASRSidecarProcessRunning, @unchecked Sendable {
    private let lock = NSLock()
    private var requests: [ASRSidecarProcessRequest] = []
    private let handler: @Sendable (ASRSidecarProcessRequest) async throws -> ASRSidecarProcessOutput

    init(output: ASRSidecarProcessOutput) {
        handler = { _ in output }
    }

    init(handler: @escaping @Sendable (ASRSidecarProcessRequest) async throws -> ASRSidecarProcessOutput) {
        self.handler = handler
    }

    var recordedRequests: [ASRSidecarProcessRequest] {
        lock.lock()
        defer { lock.unlock() }
        return requests
    }

    func run(_ request: ASRSidecarProcessRequest) async throws -> ASRSidecarProcessOutput {
        record(request)
        return try await handler(request)
    }

    private func record(_ request: ASRSidecarProcessRequest) {
        lock.lock()
        requests.append(request)
        lock.unlock()
    }
}
