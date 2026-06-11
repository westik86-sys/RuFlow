import SwiftUI

@MainActor
final class FloatingPillState: ObservableObject {
    @Published var message = ""
    @Published var showsControls = false

    var onStop: (() -> Void)?
    var onCancel: (() -> Void)?

    func showMessage(_ message: String) {
        self.message = message
        showsControls = false
        onStop = nil
        onCancel = nil
    }

    func showRecording(
        message: String,
        onStop: @escaping () -> Void,
        onCancel: @escaping () -> Void
    ) {
        self.message = message
        self.onStop = onStop
        self.onCancel = onCancel
        showsControls = true
    }
}

struct FloatingPillView: View {
    @ObservedObject var state: FloatingPillState

    var body: some View {
        HStack(spacing: 14) {
            Text(state.message)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.85)

            if state.showsControls {
                Divider()
                    .frame(height: 24)
                    .overlay(Color.white.opacity(0.18))

                if let onStop = state.onStop {
                    Button(action: onStop) {
                        Image(systemName: "stop.fill")
                            .font(.system(size: 13, weight: .bold))
                            .frame(width: 30, height: 30)
                    }
                    .buttonStyle(PillIconButtonStyle())
                    .help("Остановить запись")
                }

                if let onCancel = state.onCancel {
                    Button(action: onCancel) {
                        Image(systemName: "xmark")
                            .font(.system(size: 13, weight: .bold))
                            .frame(width: 30, height: 30)
                    }
                    .buttonStyle(PillIconButtonStyle())
                    .help("Отменить запись")
                }
            }
        }
        .padding(.horizontal, state.showsControls ? 16 : 24)
        .frame(height: 52)
        .background(
            Capsule()
                .fill(Color.black.opacity(0.84))
        )
        .overlay(
            Capsule()
                .stroke(Color.white.opacity(0.14), lineWidth: 1)
        )
        .shadow(color: Color.black.opacity(0.22), radius: 18, y: 8)
    }
}

private struct PillIconButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(.white)
            .background(
                Circle()
                    .fill(configuration.isPressed ? Color.white.opacity(0.26) : Color.white.opacity(0.14))
            )
            .contentShape(Circle())
    }
}
