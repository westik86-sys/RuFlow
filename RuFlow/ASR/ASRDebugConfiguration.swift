import Foundation

struct ASRDebugConfiguration: Sendable {
    let pythonPath: String
    let runnerPath: String

    var pythonPathForDisplay: String {
        pythonPath.isEmpty ? "Не задан" : pythonPath
    }

    var runnerPathForDisplay: String {
        runnerPath.isEmpty ? "Не задан" : runnerPath
    }

    static var current: ASRDebugConfiguration {
        ASRDebugConfiguration(
            pythonPath: pathValue(for: "RuFlowASRPythonPath"),
            runnerPath: pathValue(for: "RuFlowASRRunnerPath")
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
}
