import AppKit
import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var dictationController: DictationController
    @State private var permissionPollingTask: Task<Void, Never>?
    @State private var showsAdvancedSettings = false
    @State private var showsChangelog = false
    @State private var startsAtLogin = LoginLaunchAgentService.isEnabled
    @State private var startAtLoginErrorMessage: String?

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
            refreshStartAtLoginState()
            refreshPermissionsAndUpdatePolling()
        }
        .onDisappear {
            stopPermissionPolling()
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            refreshPermissionsAndUpdatePolling()
        }
        .sheet(isPresented: $showsChangelog) {
            ChangelogSheetView(entries: RuFlowChangelog.entries)
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

            HStack(spacing: 4) {
                Text("Версия \(appVersionText)")
                    .foregroundStyle(.secondary)
                Text("·")
                    .foregroundStyle(.secondary)
                Button("Что нового") {
                    showsChangelog = true
                }
                .buttonStyle(.link)
                .pointingHandCursor()
            }
        }
        .font(.body)
    }

    private var appVersionText: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
            ?? RuFlowChangelog.latestVersion
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
                Text("Автозапуск")
                    .foregroundStyle(.secondary)
                Toggle("Запускать RuFlow при входе в систему", isOn: startsAtLoginBinding)
                    .toggleStyle(.checkbox)
            }

            if let startAtLoginErrorMessage {
                GridRow {
                    Text("")
                    Text(startAtLoginErrorMessage)
                        .foregroundStyle(.red)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

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
            refreshStartAtLoginState()
            showsAdvancedSettings.toggle()
        }
    }

    private var startsAtLoginBinding: Binding<Bool> {
        Binding(
            get: {
                startsAtLogin
            },
            set: { isEnabled in
                updateStartsAtLogin(isEnabled)
            }
        )
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

    private func refreshStartAtLoginState() {
        startsAtLogin = LoginLaunchAgentService.isEnabled
    }

    private func updateStartsAtLogin(_ isEnabled: Bool) {
        do {
            try LoginLaunchAgentService.setEnabled(isEnabled)
            startAtLoginErrorMessage = nil
        } catch {
            startAtLoginErrorMessage = error.localizedDescription
        }

        refreshStartAtLoginState()
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

struct ChangelogEntry: Identifiable, Equatable {
    let version: String
    let dateText: String
    let sections: [ChangelogSection]

    var id: String {
        version
    }
}

struct ChangelogSection: Identifiable, Equatable {
    let title: String
    let items: [ChangelogItem]

    var id: String {
        title
    }
}

struct ChangelogItem: Identifiable, Equatable {
    let text: String

    var id: String {
        text
    }
}

enum RuFlowChangelog {
    static let entries = [
        ChangelogEntry(
            version: "1.0",
            dateText: "16 июня 2026",
            sections: [
                ChangelogSection(
                    title: "Добавлено",
                    items: [
                        ChangelogItem(text: "Настройка автозапуска RuFlow при входе в систему.")
                    ]
                ),
                ChangelogSection(
                    title: "Улучшено",
                    items: [
                        ChangelogItem(text: "Диктовка начинается только после появления индикатора на экране."),
                        ChangelogItem(text: "У одиночных распознанных фраз убирается лишняя точка в конце.")
                    ]
                ),
                ChangelogSection(
                    title: "Исправлено",
                    items: [
                        ChangelogItem(text: "Индикатор диктовки больше не должен пропадать за пределы экрана."),
                        ChangelogItem(text: "Запись корректно отменяется, если индикатор не появился или пропал во время диктовки.")
                    ]
                )
            ]
        )
    ]

    static var latestVersion: String {
        entries.first?.version ?? "1.0"
    }
}

private struct ChangelogSheetView: View {
    let entries: [ChangelogEntry]
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("История изменений")
                    .font(.title3.weight(.semibold))
                Spacer()
                Button("Закрыть") {
                    dismiss()
                }
                .keyboardShortcut(.cancelAction)
            }
            .padding(.top, 20)
            .padding(.horizontal, 24)
            .padding(.bottom, 12)

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    ForEach(entries) { entry in
                        ChangelogEntryView(entry: entry)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(24)
            }
        }
        .frame(width: 560)
        .frame(minHeight: 440)
    }
}

private struct ChangelogEntryView: View {
    let entry: ChangelogEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                Text("RuFlow \(entry.version)")
                    .font(.headline)
                Text(entry.dateText)
                    .foregroundStyle(.secondary)
                Spacer()
            }

            VStack(alignment: .leading, spacing: 14) {
                ForEach(entry.sections) { section in
                    ChangelogSectionView(section: section)
                }
            }
        }
    }
}

private struct ChangelogSectionView: View {
    let section: ChangelogSection

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(section.title)
                .font(.subheadline.weight(.semibold))

            VStack(alignment: .leading, spacing: 5) {
                ForEach(section.items) { item in
                    HStack(alignment: .top, spacing: 8) {
                        Text("•")
                            .foregroundStyle(.secondary)
                        Text(item.text)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }
}

enum LoginLaunchAgentService {
    static let label = "com.ruflow.RuFlow.login"
    static let appBundleIdentifier = "com.ruflow.RuFlow"

    static var isEnabled: Bool {
        FileManager.default.fileExists(atPath: launchAgentURL.path)
    }

    static var launchAgentURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library", isDirectory: true)
            .appendingPathComponent("LaunchAgents", isDirectory: true)
            .appendingPathComponent("\(label).plist", isDirectory: false)
    }

    static func setEnabled(_ isEnabled: Bool) throws {
        if isEnabled {
            try install()
        } else {
            try uninstall()
        }
    }

    static func propertyList(bundleIdentifier: String = appBundleIdentifier) -> [String: Any] {
        [
            "Label": label,
            "ProgramArguments": [
                "/usr/bin/open",
                "-b",
                bundleIdentifier
            ],
            "RunAtLoad": true,
            "LimitLoadToSessionType": "Aqua"
        ]
    }

    static func plistData(bundleIdentifier: String = appBundleIdentifier) throws -> Data {
        try PropertyListSerialization.data(
            fromPropertyList: propertyList(bundleIdentifier: bundleIdentifier),
            format: .xml,
            options: 0
        )
    }

    private static func install() throws {
        let fileManager = FileManager.default
        let directoryURL = launchAgentURL.deletingLastPathComponent()

        try fileManager.createDirectory(
            at: directoryURL,
            withIntermediateDirectories: true
        )

        try plistData().write(to: launchAgentURL, options: .atomic)
        try fileManager.setAttributes(
            [.posixPermissions: 0o644],
            ofItemAtPath: launchAgentURL.path
        )
    }

    private static func uninstall() throws {
        guard isEnabled else {
            return
        }

        try FileManager.default.removeItem(at: launchAgentURL)
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
