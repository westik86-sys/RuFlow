import AVFoundation

enum MicrophonePermission {
    static var authorizationStatus: AVAuthorizationStatus {
        AVCaptureDevice.authorizationStatus(for: .audio)
    }

    static var isAuthorized: Bool {
        authorizationStatus == .authorized
    }

    static var hasAvailableInput: Bool {
        AVCaptureDevice.default(for: .audio) != nil
    }

    static func requestIfNeeded() async -> Bool {
        switch authorizationStatus {
        case .authorized:
            return true
        case .notDetermined:
            return await withCheckedContinuation { continuation in
                AVCaptureDevice.requestAccess(for: .audio) { isGranted in
                    continuation.resume(returning: isGranted)
                }
            }
        case .denied, .restricted:
            return false
        @unknown default:
            return false
        }
    }

    static func statusText(for status: AVAuthorizationStatus) -> String {
        switch status {
        case .authorized:
            return "Разрешено"
        case .notDetermined:
            return "Не запрошено"
        case .denied:
            return "Запрещено"
        case .restricted:
            return "Ограничено"
        @unknown default:
            return "Неизвестно"
        }
    }
}
