import AVFoundation
import Foundation

enum AudioRecordingError: LocalizedError {
    case microphonePermissionDenied
    case microphoneUnavailable
    case applicationSupportUnavailable
    case couldNotCreateRecordingsDirectory
    case couldNotStartRecording
    case noActiveRecording
    case outputFileMissing
    case recorderFailure(String)

    var errorDescription: String? {
        switch self {
        case .microphonePermissionDenied:
            return "Нет разрешения на микрофон"
        case .microphoneUnavailable:
            return "Микрофон не найден"
        case .applicationSupportUnavailable:
            return "Не удалось найти Application Support"
        case .couldNotCreateRecordingsDirectory:
            return "Не удалось создать папку записей"
        case .couldNotStartRecording:
            return "Не удалось начать запись"
        case .noActiveRecording:
            return "Нет активной записи"
        case .outputFileMissing:
            return "Файл записи не был создан"
        case .recorderFailure(let message):
            return message
        }
    }
}

final class AudioRecordingService: NSObject {
    private var recorder: AVAudioRecorder?
    private var currentFileURL: URL?
    private let fileManager: FileManager

    init(fileManager: FileManager = .default) {
        self.fileManager = fileManager
        super.init()
    }

    var recordingsDirectory: URL? {
        guard let applicationSupportURL = fileManager.urls(
            for: .applicationSupportDirectory,
            in: .userDomainMask
        ).first else {
            return nil
        }

        return applicationSupportURL
            .appendingPathComponent("RuFlow", isDirectory: true)
            .appendingPathComponent("Recordings", isDirectory: true)
    }

    func startRecording() throws {
        guard MicrophonePermission.isAuthorized else {
            throw AudioRecordingError.microphonePermissionDenied
        }

        guard MicrophonePermission.hasAvailableInput else {
            throw AudioRecordingError.microphoneUnavailable
        }

        if recorder?.isRecording == true {
            cancelRecording()
        }

        guard let directoryURL = recordingsDirectory else {
            throw AudioRecordingError.applicationSupportUnavailable
        }

        do {
            try fileManager.createDirectory(
                at: directoryURL,
                withIntermediateDirectories: true
            )
        } catch {
            throw AudioRecordingError.couldNotCreateRecordingsDirectory
        }

        let outputURL = directoryURL.appendingPathComponent(Self.fileName(), isDirectory: false)
        let recorder = try makeRecorder(outputURL: outputURL)
        recorder.isMeteringEnabled = true
        recorder.prepareToRecord()

        guard recorder.record() else {
            throw AudioRecordingError.couldNotStartRecording
        }

        self.recorder = recorder
        currentFileURL = outputURL
    }

    func normalizedMeterLevel() -> Double {
        guard let recorder, recorder.isRecording else {
            return 0
        }

        recorder.updateMeters()

        let minimumDecibels: Float = -55
        let maximumDecibels: Float = -8
        let averagePower = recorder.averagePower(forChannel: 0)

        guard averagePower > minimumDecibels else {
            return 0
        }

        let clampedPower = min(averagePower, maximumDecibels)
        let linearLevel = Double((clampedPower - minimumDecibels) / (maximumDecibels - minimumDecibels))
        return pow(linearLevel, 0.65)
    }

    func stopRecording() throws -> URL {
        guard let recorder, let outputURL = currentFileURL else {
            throw AudioRecordingError.noActiveRecording
        }

        recorder.stop()
        self.recorder = nil
        currentFileURL = nil

        guard fileManager.fileExists(atPath: outputURL.path) else {
            throw AudioRecordingError.outputFileMissing
        }

        return outputURL
    }

    func cancelRecording() {
        let outputURL = currentFileURL
        recorder?.stop()
        recorder = nil
        currentFileURL = nil

        if let outputURL {
            removeRecording(at: outputURL)
        }
    }

    func removeRecording(at outputURL: URL) {
        try? fileManager.removeItem(at: outputURL)
    }

    private func makeRecorder(outputURL: URL) throws -> AVAudioRecorder {
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: 16_000.0,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsNonInterleaved: false
        ]

        do {
            return try AVAudioRecorder(url: outputURL, settings: settings)
        } catch {
            throw AudioRecordingError.recorderFailure(error.localizedDescription)
        }
    }

    private static func fileName() -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd-HHmmss-SSS"
        return "ruflow-\(formatter.string(from: Date())).wav"
    }
}
