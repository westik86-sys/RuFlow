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

enum ASRSidecarError: LocalizedError, Sendable {
    case pythonPathMissing
    case runnerPathMissing
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

final class ASRSidecarService: Sendable {
    func transcribe(
        audioURL: URL,
        configuration: ASRDebugConfiguration
    ) async throws -> ASRSidecarResult {
        try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    let result = try Self.runSidecar(
                        audioURL: audioURL,
                        configuration: configuration
                    )
                    continuation.resume(returning: result)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private static func runSidecar(
        audioURL: URL,
        configuration: ASRDebugConfiguration
    ) throws -> ASRSidecarResult {
        let expectedModel = "gigaam-v3-e2e-rnnt"
        let fileManager = FileManager.default
        let pythonPath = configuration.pythonPath
        let runnerPath = configuration.runnerPath
        let audioPath = audioURL.path

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

        guard fileManager.fileExists(atPath: audioPath) else {
            throw ASRSidecarError.audioFileMissing(audioPath)
        }

        let process = Process()
        let stdout = Pipe()
        let stderr = Pipe()

        process.executableURL = URL(fileURLWithPath: pythonPath)
        process.arguments = [runnerPath, audioPath]
        process.currentDirectoryURL = URL(fileURLWithPath: runnerPath).deletingLastPathComponent()
        process.standardOutput = stdout
        process.standardError = stderr

        do {
            try process.run()
        } catch {
            throw ASRSidecarError.launchFailed(error.localizedDescription)
        }

        process.waitUntilExit()

        let stdoutData = stdout.fileHandleForReading.readDataToEndOfFile()
        let stderrData = stderr.fileHandleForReading.readDataToEndOfFile()
        let stdoutText = String(data: stdoutData, encoding: .utf8) ?? ""
        let stderrText = String(data: stderrData, encoding: .utf8) ?? ""

        guard !stdoutData.isEmpty else {
            if process.terminationStatus != 0 {
                let message = shortMessage(stderrText.isEmpty ? stdoutText : stderrText)
                throw ASRSidecarError.failed(status: process.terminationStatus, message: message)
            }

            throw ASRSidecarError.emptyOutput
        }

        let response: ASRSidecarResponse
        do {
            response = try JSONDecoder().decode(ASRSidecarResponse.self, from: stdoutData)
        } catch {
            if process.terminationStatus != 0 {
                let message = shortMessage(stderrText.isEmpty ? stdoutText : stderrText)
                throw ASRSidecarError.failed(status: process.terminationStatus, message: message)
            }

            throw ASRSidecarError.invalidJSON(shortMessage(error.localizedDescription))
        }

        guard process.terminationStatus == 0 else {
            let message = shortMessage(response.error ?? stderrText)
            throw ASRSidecarError.failed(status: process.terminationStatus, message: message)
        }

        guard response.model == expectedModel else {
            throw ASRSidecarError.failed(
                status: process.terminationStatus,
                message: "неожиданная модель: \(response.model)"
            )
        }

        if response.ok == false {
            throw ASRSidecarError.failed(
                status: process.terminationStatus,
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
