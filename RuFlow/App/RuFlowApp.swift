import SwiftUI

@main
struct RuFlowApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var dictationController = DictationController()

    var body: some Scene {
        MenuBarExtra("RuFlow", systemImage: dictationController.menuBarSystemImage) {
            MenuBarContentView()
                .environmentObject(dictationController)
        }
        .menuBarExtraStyle(.menu)

        Settings {
            SettingsView()
                .environmentObject(dictationController)
        }
    }
}

private struct MenuBarContentView: View {
    @Environment(\.openSettings) private var openSettings
    @EnvironmentObject private var dictationController: DictationController

    var body: some View {
        Text(dictationController.menuStatusText)

        Divider()

        Button("Настройки...") {
            NSApp.activate(ignoringOtherApps: true)
            openSettings()
        }

        Button("Запросить Accessibility") {
            AccessibilityPermission.request()
            dictationController.refreshPermissionsAndHotkey()
        }

        Button("Запросить микрофон") {
            dictationController.requestMicrophoneAccessIfNeeded()
        }

        Divider()

        Button("Выход") {
            NSApp.terminate(nil)
        }
        .keyboardShortcut("q")
    }
}
