import AppKit
import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var dictationController: DictationController
    @State private var permissionPollingTask: Task<Void, Never>?
    @State private var showsAdvancedSettings = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("RuFlow")
                        .font(.title2.weight(.semibold))
                    HStack(spacing: 0) {
                        Text("Это как ")
                            .foregroundStyle(.secondary)
                        Link("wisprflow.ai", destination: URL(string: "https://wisprflow.ai/")!)
                            .pointingHandCursor()
                        Text(", только бесплатно и локально на вашем Mac")
                            .foregroundStyle(.secondary)
                    }
                }

                Divider()

                Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 12) {
                    GridRow {
                        Text("Горячая клавиша")
                            .foregroundStyle(.secondary)
                        Text("Option + Space, удерживать")
                    }

                    GridRow {
                        Text("Accessibility")
                            .foregroundStyle(.secondary)
                        if dictationController.isAccessibilityTrusted {
                            Text(dictationController.accessibilityStatusText)
                        } else {
                            accessibilityPermissionButton
                        }
                    }

                    GridRow {
                        Text("Микрофон")
                            .foregroundStyle(.secondary)
                        if dictationController.canRequestMicrophonePermission {
                            microphonePermissionButton
                        } else {
                            Text(dictationController.microphoneStatusText)
                        }
                    }

                }

                HStack {
                    refreshButton
                    advancedSettingsButton
                }

                if showsAdvancedSettings {
                    advancedSettingsGrid
                }

                Text("Для глобального hotkey и synthetic Cmd+V macOS должна разрешить приложению управление компьютером в System Settings -> Privacy & Security -> Accessibility. Для записи WAV нужен доступ к микрофону в Privacy & Security -> Microphone.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                if !dictationController.isAccessibilityTrusted {
                    Text("Если RuFlow включен в Accessibility, но здесь всё равно написано \"Требуется\", удалите RuFlow из списка Accessibility через кнопку минус, затем добавьте именно приложение из строки \"Запущено из\" в разделе \"Дополнительно\" и полностью перезапустите RuFlow.")
                        .font(.footnote)
                        .foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if dictationController.isMicrophonePermissionDenied {
                    Text("Доступ к микрофону запрещен. Включите RuFlow в System Settings -> Privacy & Security -> Microphone, затем вернитесь сюда.")
                        .font(.footnote)
                        .foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 24)

                settingsFooter
            }
            .frame(maxWidth: .infinity, minHeight: 512, alignment: .topLeading)
            .padding(24)
        }
        .frame(width: 680)
        .frame(minHeight: 560)
        .onAppear {
            refreshPermissionsAndUpdatePolling()
        }
        .onDisappear {
            stopPermissionPolling()
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            refreshPermissionsAndUpdatePolling()
        }
    }

    private var settingsFooter: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 0) {
                Text("Запилено мной ")
                    .foregroundStyle(.secondary)
                Link("@korostelevpavel", destination: URL(string: "https://t.me/korostelevpavel")!)
                    .pointingHandCursor()
            }

            Text("Если нашли баг или хотите предложить улучшение — напишите мне 🤙🏻")
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .font(.body)
    }

    private var accessibilityPermissionButton: some View {
        Button("Запросить разрешение") {
            AccessibilityPermission.request()
            dictationController.refreshPermissionsAndHotkey()
        }
        .controlSize(.small)
    }

    private var microphonePermissionButton: some View {
        Button("Запросить разрешение") {
            dictationController.requestMicrophoneAccessIfNeeded()
        }
        .controlSize(.small)
    }

    private var advancedSettingsGrid: some View {
        Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 12) {
            GridRow {
                Text("Временные аудиофайлы")
                    .foregroundStyle(.secondary)
                Button {
                    openTemporaryAudioFilesDirectory()
                } label: {
                    Text(dictationController.recordingsDirectoryPath)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                }
                .buttonStyle(.link)
                .pointingHandCursor()
                .help("Открыть папку временных аудиофайлов")
            }

            GridRow {
                Text("Python")
                    .foregroundStyle(.secondary)
                Text(dictationController.asrPythonPath)
                    .lineLimit(2)
                    .textSelection(.enabled)
            }

            GridRow {
                Text("ASR runner")
                    .foregroundStyle(.secondary)
                Text(dictationController.asrRunnerPath)
                    .lineLimit(3)
                    .textSelection(.enabled)
            }

            GridRow {
                Text("Запущено из")
                    .foregroundStyle(.secondary)
                Text(dictationController.runningAppPath)
                    .lineLimit(3)
                    .textSelection(.enabled)
            }
        }
    }

    private var refreshButton: some View {
        Button("Проверить снова") {
            dictationController.refreshPermissionsAndHotkey()
            updatePermissionPolling()
        }
    }

    private var advancedSettingsButton: some View {
        Button(showsAdvancedSettings ? "Скрыть" : "Дополнительно") {
            showsAdvancedSettings.toggle()
        }
    }

    private func refreshPermissionsAndUpdatePolling() {
        dictationController.refreshPermissionStatus()
        updatePermissionPolling()
    }

    private func updatePermissionPolling() {
        if dictationController.needsPermissionPolling {
            startPermissionPolling()
        } else {
            stopPermissionPolling()
        }
    }

    private func startPermissionPolling() {
        guard permissionPollingTask == nil else {
            return
        }

        permissionPollingTask = Task { @MainActor in
            while !Task.isCancelled {
                do {
                    try await Task.sleep(for: .seconds(1))
                } catch {
                    return
                }

                dictationController.refreshPermissionStatus()

                if !dictationController.needsPermissionPolling {
                    permissionPollingTask = nil
                    return
                }
            }
        }
    }

    private func stopPermissionPolling() {
        permissionPollingTask?.cancel()
        permissionPollingTask = nil
    }

    private func openTemporaryAudioFilesDirectory() {
        guard let directoryURL = dictationController.recordingsDirectoryURL else {
            return
        }

        do {
            try FileManager.default.createDirectory(
                at: directoryURL,
                withIntermediateDirectories: true
            )
        } catch {
            return
        }

        NSWorkspace.shared.open(directoryURL)
    }
}

private struct PointingHandCursorModifier: ViewModifier {
    @State private var isPointingHandCursorActive = false

    func body(content: Content) -> some View {
        content
            .onHover { isHovering in
                if isHovering {
                    pushPointingHandCursorIfNeeded()
                } else {
                    popPointingHandCursorIfNeeded()
                }
            }
            .onDisappear {
                popPointingHandCursorIfNeeded()
            }
    }

    private func pushPointingHandCursorIfNeeded() {
        guard !isPointingHandCursorActive else {
            return
        }

        NSCursor.pointingHand.push()
        isPointingHandCursorActive = true
    }

    private func popPointingHandCursorIfNeeded() {
        guard isPointingHandCursorActive else {
            return
        }

        NSCursor.pop()
        isPointingHandCursorActive = false
    }
}

private extension View {
    func pointingHandCursor() -> some View {
        modifier(PointingHandCursorModifier())
    }
}
