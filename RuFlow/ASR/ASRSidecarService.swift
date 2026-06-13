import Darwin
import Foundation

struct ASRSidecarResult: Decodable, Sendable {
    let text: String
    let durationMs: Int
    let model: String

    enum CodingKeys: String, CodingKey {
        case text
        case durationMs = "duration_ms"
        case model
    }
}

private struct ASRSidecarResponse: Decodable {
    let ok: Bool?
    let text: String?
    let error: String?
    let durationMs: Int?
    let model: String

    enum CodingKeys: String, CodingKey {
        case ok
        case text
        case error
        case durationMs = "duration_ms"
        case model
    }
}

enum ASRSidecarResponseParser {
    private static let expectedModel = "gigaam-v3-e2e-rnnt"

    static func parse(
        stdoutData: Data,
        stderrText: String,
        terminationStatus: Int32
    ) throws -> ASRSidecarResult {
        let stdoutText = String(data: stdoutData, encoding: .utf8) ?? ""

        guard !stdoutData.isEmpty else {
            if terminationStatus != 0 {
                let message = shortMessage(stderrText.isEmpty ? stdoutText : stderrText)
                throw ASRSidecarError.failed(status: terminationStatus, message: message)
            }

            throw ASRSidecarError.emptyOutput
        }

        let response: ASRSidecarResponse
        do {
            response = try JSONDecoder().decode(ASRSidecarResponse.self, from: stdoutData)
        } catch {
            if terminationStatus != 0 {
                let message = shortMessage(stderrText.isEmpty ? stdoutText : stderrText)
                throw ASRSidecarError.failed(status: terminationStatus, message: message)
            }

            throw ASRSidecarError.invalidJSON(shortMessage(error.localizedDescription))
        }

        guard terminationStatus == 0 else {
            let message = shortMessage(response.error ?? stderrText)
            throw ASRSidecarError.failed(status: terminationStatus, message: message)
        }

        guard response.model == expectedModel else {
            throw ASRSidecarError.failed(
                status: terminationStatus,
                message: "неожиданная модель: \(response.model)"
            )
        }

        if response.ok == false {
            throw ASRSidecarError.failed(
                status: terminationStatus,
                message: shortMessage(response.error ?? "sidecar вернул ok=false")
            )
        }

        guard let text = response.text?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else {
            throw ASRSidecarError.emptyText
        }

        return ASRSidecarResult(
            text: text,
            durationMs: response.durationMs ?? 0,
            model: response.model
        )
    }

    private static func shortMessage(_ message: String) -> String {
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return "неизвестная ошибка"
        }

        if trimmed.count <= 180 {
            return trimmed
        }

        let endIndex = trimmed.index(trimmed.startIndex, offsetBy: 180)
        return String(trimmed[..<endIndex])
    }
}

enum ASRSidecarError: LocalizedError, Sendable {
    case pythonPathMissing
    case runnerPathMissing
    case sidecarNotFound(String)
    case modelDirectoryNotFound(String)
    case pythonNotFound(String)
    case runnerNotFound(String)
    case audioFileMissing(String)
    case launchFailed(String)
    case failed(status: Int32, message: String)
    case emptyOutput
    case invalidJSON(String)
    case emptyText

    var errorDescription: String? {
        switch self {
        case .pythonPathMissing:
            return "ASR: путь к Python не задан"
        case .runnerPathMissing:
            return "ASR: путь к runner.py не задан"
        case .sidecarNotFound(let path):
            return "ASR: sidecar не найден: \(path)"
        case .modelDirectoryNotFound(let path):
            return "ASR: модель не найдена: \(path)"
        case .pythonNotFound(let path):
            return "ASR: Python не найден: \(path)"
        case .runnerNotFound(let path):
            return "ASR: runner.py не найден: \(path)"
        case .audioFileMissing(let path):
            return "ASR: WAV не найден: \(path)"
        case .launchFailed(let message):
            return "ASR: не удалось запустить sidecar: \(message)"
        case .failed(_, let message):
            return "ASR: \(message)"
        case .emptyOutput:
            return "ASR: sidecar не вернул JSON"
        case .invalidJSON(let message):
            return "ASR: неверный JSON: \(message)"
        case .emptyText:
            return "ASR: текст не распознан"
        }
    }
}

struct ASRSidecarProcessRequest: Sendable {
    let executableURL: URL
    let arguments: [String]
    let currentDirectoryURL: URL
    let environment: [String: String]?
}

struct ASRSidecarProcessOutput: Sendable {
    let stdoutData: Data
    let stderrText: String
    let terminationStatus: Int32
}

protocol ASRSidecarProcessRunning: Sendable {
    func run(_ request: ASRSidecarProcessRequest) async throws -> ASRSidecarProcessOutput
}

private final class ASRSidecarPipeCollector: @unchecked Sendable {
    private let fileHandle: FileHandle
    private let lock = NSLock()
    private var bufferedData = Data()
    private var isFinished = false
    private var continuations: [CheckedContinuation<Data, Never>] = []

    init(fileHandle: FileHandle) {
        self.fileHandle = fileHandle
    }

    func start() {
        fileHandle.readabilityHandler = { [weak self] fileHandle in
            let data = fileHandle.availableData
            if data.isEmpty {
                self?.finish(closeFile: false)
            } else {
                self?.append(data)
            }
        }
    }

    func readToEnd() async -> Data {
        await withCheckedContinuation { continuation in
            lock.lock()
            if isFinished {
                let data = bufferedData
                lock.unlock()
                continuation.resume(returning: data)
            } else {
                continuations.append(continuation)
                lock.unlock()
            }
        }
    }

    func close() {
        finish(closeFile: true)
    }

    private func append(_ data: Data) {
        lock.lock()
        if !isFinished {
            bufferedData.append(data)
        }
        lock.unlock()
    }

    private func finish(closeFile: Bool) {
        let data: Data
        let continuations: [CheckedContinuation<Data, Never>]

        lock.lock()
        guard !isFinished else {
            lock.unlock()
            return
        }

        isFinished = true
        data = bufferedData
        continuations = self.continuations
        self.continuations = []
        lock.unlock()

        fileHandle.readabilityHandler = nil
        if closeFile {
            try? fileHandle.close()
        }

        for continuation in continuations {
            continuation.resume(returning: data)
        }
    }
}

final class ASRSidecarProcessRunner: ASRSidecarProcessRunning {
    func run(_ request: ASRSidecarProcessRequest) async throws -> ASRSidecarProcessOutput {
        let execution = ASRSidecarProcessExecution(request: request)

        return try await withTaskCancellationHandler {
            try await execution.run()
        } onCancel: {
            execution.cancel()
        }
    }
}

private final class ASRSidecarProcessExecution: @unchecked Sendable {
    private let request: ASRSidecarProcessRequest
    private let process = Process()
    private let lock = NSLock()
    private var stdoutCollector: ASRSidecarPipeCollector?
    private var stderrCollector: ASRSidecarPipeCollector?
    private var terminationContinuation: CheckedContinuation<Int32, Error>?
    private var hasStarted = false
    private var hasProcessTerminated = false
    private var hasResumedTermination = false
    private var isFinished = false
    private var hasCancelled = false

    init(request: ASRSidecarProcessRequest) {
        self.request = request
    }

    func run() async throws -> ASRSidecarProcessOutput {
        let stdout = Pipe()
        let stderr = Pipe()
        let stdoutCollector = ASRSidecarPipeCollector(fileHandle: stdout.fileHandleForReading)
        let stderrCollector = ASRSidecarPipeCollector(fileHandle: stderr.fileHandleForReading)

        setCollectors(stdout: stdoutCollector, stderr: stderrCollector)
        defer {
            finishExecution()
        }

        stdoutCollector.start()
        stderrCollector.start()

        process.executableURL = request.executableURL
        process.arguments = request.arguments
        process.currentDirectoryURL = request.currentDirectoryURL
        process.environment = request.environment
        process.standardOutput = stdout
        process.standardError = stderr

        let terminationStatus: Int32
        do {
            terminationStatus = try await runProcess()
        } catch {
            throw error
        }

        let stdoutData = await stdoutCollector.readToEnd()
        let stderrData = await stderrCollector.readToEnd()
        let stderrText = String(data: stderrData, encoding: .utf8) ?? ""

        if wasCancelled {
            throw CancellationError()
        }

        return ASRSidecarProcessOutput(
            stdoutData: stdoutData,
            stderrText: stderrText,
            terminationStatus: terminationStatus
        )
    }

    func cancel() {
        let pidToKill: pid_t?
        let stdoutCollector: ASRSidecarPipeCollector?
        let stderrCollector: ASRSidecarPipeCollector?

        lock.lock()
        hasCancelled = true
        let shouldCloseCollectors = !isFinished
        stdoutCollector = shouldCloseCollectors ? self.stdoutCollector : nil
        stderrCollector = shouldCloseCollectors ? self.stderrCollector : nil
        let shouldTerminate = hasStarted && !hasProcessTerminated && process.isRunning
        pidToKill = shouldTerminate ? process.processIdentifier : nil
        lock.unlock()

        stdoutCollector?.close()
        stderrCollector?.close()

        guard let pidToKill else {
            return
        }

        process.terminate()

        DispatchQueue.global(qos: .userInitiated).asyncAfter(deadline: .now() + 1) { [weak self] in
            self?.killIfStillRunning(pid: pidToKill)
        }
    }

    private func runProcess() async throws -> Int32 {
        try await withCheckedThrowingContinuation { continuation in
            setTerminationContinuation(continuation)

            process.terminationHandler = { [weak self] process in
                self?.resumeTermination(.success(process.terminationStatus))
            }

            if wasCancelled {
                resumeTermination(.failure(CancellationError()))
                return
            }

            do {
                try process.run()
                markStarted()

                if wasCancelled {
                    cancel()
                }
            } catch {
                resumeTermination(.failure(ASRSidecarError.launchFailed(error.localizedDescription)))
            }
        }
    }

    private var wasCancelled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return hasCancelled
    }

    private func setCollectors(
        stdout: ASRSidecarPipeCollector,
        stderr: ASRSidecarPipeCollector
    ) {
        lock.lock()
        stdoutCollector = stdout
        stderrCollector = stderr
        lock.unlock()
    }

    private func setTerminationContinuation(_ continuation: CheckedContinuation<Int32, Error>) {
        lock.lock()
        terminationContinuation = continuation
        lock.unlock()
    }

    private func markStarted() {
        lock.lock()
        hasStarted = true
        lock.unlock()
    }

    private func resumeTermination(_ result: Result<Int32, Error>) {
        let continuation: CheckedContinuation<Int32, Error>?

        lock.lock()
        guard !hasResumedTermination else {
            lock.unlock()
            return
        }

        hasResumedTermination = true
        hasProcessTerminated = true
        continuation = terminationContinuation
        terminationContinuation = nil
        lock.unlock()

        switch result {
        case .success(let status):
            continuation?.resume(returning: status)
        case .failure(let error):
            continuation?.resume(throwing: error)
        }
    }

    private func finishExecution() {
        let stdoutCollector: ASRSidecarPipeCollector?
        let stderrCollector: ASRSidecarPipeCollector?

        lock.lock()
        isFinished = true
        stdoutCollector = self.stdoutCollector
        stderrCollector = self.stderrCollector
        self.stdoutCollector = nil
        self.stderrCollector = nil
        process.terminationHandler = nil
        lock.unlock()

        stdoutCollector?.close()
        stderrCollector?.close()
    }

    private func killIfStillRunning(pid: pid_t) {
        lock.lock()
        let shouldKill = hasStarted
            && !hasProcessTerminated
            && process.isRunning
            && process.processIdentifier == pid
        lock.unlock()

        if shouldKill {
            Darwin.kill(pid, SIGKILL)
        }
    }
}

final class ASRSidecarService: Sendable {
    private let processRunner: ASRSidecarProcessRunning

    init(processRunner: ASRSidecarProcessRunning = ASRSidecarProcessRunner()) {
        self.processRunner = processRunner
    }

    func transcribe(
        audioURL: URL,
        configuration: ASRDebugConfiguration
    ) async throws -> ASRSidecarResult {
        try await runSidecar(audioURL: audioURL, configuration: configuration)
    }

    private func runSidecar(
        audioURL: URL,
        configuration: ASRDebugConfiguration
    ) async throws -> ASRSidecarResult {
        let fileManager = FileManager.default
        let pythonPath = configuration.pythonPath
        let runnerPath = configuration.runnerPath
        let sidecarExecutablePath = configuration.sidecarExecutablePath
        let modelDirectoryPath = configuration.modelDirectoryPath
        let audioPath = audioURL.path

        guard fileManager.fileExists(atPath: audioPath) else {
            throw ASRSidecarError.audioFileMissing(audioPath)
        }

        let executableURL: URL
        let arguments: [String]
        let currentDirectoryURL: URL

        if !sidecarExecutablePath.isEmpty {
            guard fileManager.isExecutableFile(atPath: sidecarExecutablePath) else {
                throw ASRSidecarError.sidecarNotFound(sidecarExecutablePath)
            }

            var isModelDirectory = ObjCBool(false)
            guard !modelDirectoryPath.isEmpty,
                  fileManager.fileExists(atPath: modelDirectoryPath, isDirectory: &isModelDirectory),
                  isModelDirectory.boolValue else {
                throw ASRSidecarError.modelDirectoryNotFound(modelDirectoryPath)
            }

            executableURL = URL(fileURLWithPath: sidecarExecutablePath)
            arguments = [audioPath]
            currentDirectoryURL = executableURL.deletingLastPathComponent()
        } else {
            guard !pythonPath.isEmpty else {
                throw ASRSidecarError.pythonPathMissing
            }

            guard !runnerPath.isEmpty else {
                throw ASRSidecarError.runnerPathMissing
            }

            guard fileManager.isExecutableFile(atPath: pythonPath) else {
                throw ASRSidecarError.pythonNotFound(pythonPath)
            }

            guard fileManager.fileExists(atPath: runnerPath) else {
                throw ASRSidecarError.runnerNotFound(runnerPath)
            }

            executableURL = URL(fileURLWithPath: pythonPath)
            arguments = [runnerPath, audioPath]
            currentDirectoryURL = URL(fileURLWithPath: runnerPath).deletingLastPathComponent()
        }

        let environment: [String: String]?
        if !modelDirectoryPath.isEmpty {
            var processEnvironment = ProcessInfo.processInfo.environment
            processEnvironment["RUFLOW_GIGAAM_MODEL_DIR"] = modelDirectoryPath
            processEnvironment["HF_HUB_OFFLINE"] = "1"
            environment = processEnvironment
        } else {
            environment = nil
        }

        let output = try await processRunner.run(
            ASRSidecarProcessRequest(
                executableURL: executableURL,
                arguments: arguments,
                currentDirectoryURL: currentDirectoryURL,
                environment: environment
            )
        )

        return try ASRSidecarResponseParser.parse(
            stdoutData: output.stdoutData,
            stderrText: output.stderrText,
            terminationStatus: output.terminationStatus
        )
    }
}
