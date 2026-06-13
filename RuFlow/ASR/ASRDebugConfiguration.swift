import Foundation

struct ASRDebugConfiguration: Sendable {
    let pythonPath: String
    let runnerPath: String
    let sidecarExecutablePath: String
    let modelDirectoryPath: String

    var pythonPathForDisplay: String {
        pythonPath.isEmpty ? "Не задан" : pythonPath
    }

    var runnerPathForDisplay: String {
        runnerPath.isEmpty ? "Не задан" : runnerPath
    }

    static var current: ASRDebugConfiguration {
        let bundledASRDirectory = Bundle.main.resourceURL?.appendingPathComponent("asr", isDirectory: true)
        let bundledSidecarPath = bundledASRDirectory?
            .appendingPathComponent("sidecar", isDirectory: true)
            .appendingPathComponent("runner", isDirectory: false)
            .path ?? ""
        let bundledModelPath = bundledASRDirectory?
            .appendingPathComponent("models", isDirectory: true)
            .appendingPathComponent("gigaam-v3-e2e-rnnt", isDirectory: true)
            .path ?? ""

        return ASRDebugConfiguration(
            pythonPath: pathValue(for: "RuFlowASRPythonPath"),
            runnerPath: pathValue(for: "RuFlowASRRunnerPath"),
            sidecarExecutablePath: existingExecutablePath(bundledSidecarPath),
            modelDirectoryPath: existingDirectoryPath(bundledModelPath)
        )
    }

    private static func pathValue(for key: String) -> String {
        let value = Bundle.main.object(forInfoDictionaryKey: key) as? String ?? ""
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !trimmed.isEmpty, !trimmed.contains("$(") else {
            return ""
        }

        return (trimmed as NSString).expandingTildeInPath
    }

    private static func existingExecutablePath(_ path: String) -> String {
        guard !path.isEmpty, FileManager.default.isExecutableFile(atPath: path) else {
            return ""
        }

        return path
    }

    private static func existingDirectoryPath(_ path: String) -> String {
        var isDirectory = ObjCBool(false)
        guard !path.isEmpty,
              FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory),
              isDirectory.boolValue else {
            return ""
        }

        return path
    }

}
