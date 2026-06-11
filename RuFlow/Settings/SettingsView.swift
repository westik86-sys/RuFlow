import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var dictationController: DictationController

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            VStack(alignment: .leading, spacing: 6) {
                Text("RuFlow")
                    .font(.title2.weight(.semibold))
                Text("Локальный push-to-talk диктовщик")
                    .foregroundStyle(.secondary)
            }

            Divider()

            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 12) {
                GridRow {
                    Text("Горячая клавиша")
                        .foregroundStyle(.secondary)
                    Text("Option + Space, удерживать")
                }

                GridRow {
                    Text("Статус")
                        .foregroundStyle(.secondary)
                    Text(dictationController.menuStatusText)
                }

                GridRow {
                    Text("Accessibility")
                        .foregroundStyle(.secondary)
                    Text(dictationController.isAccessibilityTrusted ? "Разрешено" : "Требуется")
                }

                GridRow {
                    Text("Микрофон")
                        .foregroundStyle(.secondary)
                    Text(dictationController.microphoneStatusText)
                }

                GridRow {
                    Text("Записи")
                        .foregroundStyle(.secondary)
                    Text(dictationController.recordingsDirectoryPath)
                        .lineLimit(2)
                        .textSelection(.enabled)
                }
            }

            ViewThatFits {
                permissionButtons

                VStack(alignment: .leading, spacing: 8) {
                    accessibilityButton
                    microphoneButton
                    refreshButton
                }
            }

            Text("Для глобального hotkey и synthetic Cmd+V macOS должна разрешить приложению управление компьютером в System Settings -> Privacy & Security -> Accessibility. Для записи WAV нужен доступ к микрофону в Privacy & Security -> Microphone.")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(24)
        .frame(width: 460)
    }

    private var permissionButtons: some View {
        HStack {
            accessibilityButton
            microphoneButton
            refreshButton
        }
    }

    private var accessibilityButton: some View {
        Button("Запросить Accessibility") {
            AccessibilityPermission.request()
            dictationController.refreshPermissionsAndHotkey()
        }
    }

    private var microphoneButton: some View {
        Button("Запросить микрофон") {
            dictationController.requestMicrophoneAccessIfNeeded()
        }
    }

    private var refreshButton: some View {
        Button("Проверить снова") {
            dictationController.refreshPermissionsAndHotkey()
        }
    }
}
