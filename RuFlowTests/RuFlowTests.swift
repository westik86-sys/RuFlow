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

private enum TestTimeoutError: Error {
    case timedOut
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
