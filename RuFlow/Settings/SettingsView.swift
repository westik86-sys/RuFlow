import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var dictationController: DictationController
    @AppStorage(UserDictionary.enabledKey) private var isUserDictionaryEnabled = UserDictionary.defaultIsEnabled
    @State private var dictionaryEntries = UserDictionary.entries

    var body: some View {
        ScrollView {
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
                        Text(dictationController.accessibilityStatusText)
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

                ViewThatFits {
                    permissionButtons

                    VStack(alignment: .leading, spacing: 8) {
                        accessibilityButton
                        microphoneButton
                        refreshButton
                    }
                }

                dictionarySection

                Text("Для глобального hotkey и synthetic Cmd+V macOS должна разрешить приложению управление компьютером в System Settings -> Privacy & Security -> Accessibility. Для записи WAV нужен доступ к микрофону в Privacy & Security -> Microphone. Пути Python и ASR runner задаются в Debug.xcconfig.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                if !dictationController.isAccessibilityTrusted {
                    Text("Если RuFlow включен в Accessibility, но здесь всё равно написано \"Требуется\", удалите RuFlow из списка Accessibility через кнопку минус, затем добавьте именно приложение из строки \"Запущено из\" и полностью перезапустите RuFlow.")
                        .font(.footnote)
                        .foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(24)
        }
        .frame(width: 680)
        .frame(minHeight: 560)
        .onChange(of: dictionaryEntries) { _, entries in
            UserDictionary.entries = entries
        }
        .onAppear {
            dictionaryEntries = UserDictionary.entries
        }
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

    private var dictionarySection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Divider()

            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Словарь")
                        .font(.headline)
                    Text("Пользовательские правила применяются после встроенного словаря.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                Toggle("Включить", isOn: $isUserDictionaryEnabled)
                    .toggleStyle(.switch)
            }

            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 8) {
                    Text("Что распознано")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Text("Замена")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Color.clear.frame(width: 28, height: 1)
                }

                ForEach($dictionaryEntries) { $entry in
                    HStack(spacing: 8) {
                        TextField("эл эл эм", text: $entry.source)
                            .textFieldStyle(.roundedBorder)
                        Image(systemName: "arrow.right")
                            .foregroundStyle(.secondary)
                            .frame(width: 18)
                        TextField("LLM", text: $entry.replacement)
                            .textFieldStyle(.roundedBorder)
                        Button {
                            removeDictionaryEntry(entry)
                        } label: {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.borderless)
                        .help("Удалить правило")
                        .frame(width: 28)
                    }
                }

                if dictionaryEntries.isEmpty {
                    Text("Пользовательских правил пока нет.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }

            Button {
                dictionaryEntries.append(UserDictionaryEntry())
            } label: {
                Label("Добавить правило", systemImage: "plus")
            }
        }
    }

    private func removeDictionaryEntry(_ entry: UserDictionaryEntry) {
        dictionaryEntries.removeAll { $0.id == entry.id }
    }
}
