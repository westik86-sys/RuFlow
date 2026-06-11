import SwiftUI

struct FloatingPillView: View {
    let message: String
    let onStop: (() -> Void)?
    let onCancel: (() -> Void)?

    init(
        message: String,
        onStop: (() -> Void)? = nil,
        onCancel: (() -> Void)? = nil
    ) {
        self.message = message
        self.onStop = onStop
        self.onCancel = onCancel
    }

    private var showsControls: Bool {
        onStop != nil || onCancel != nil
    }

    var body: some View {
        HStack(spacing: 14) {
            Text(message)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.85)

            if showsControls {
                Divider()
                    .frame(height: 24)
                    .overlay(Color.white.opacity(0.18))

                if let onStop {
                    Button(action: onStop) {
                        Image(systemName: "stop.fill")
                            .font(.system(size: 13, weight: .bold))
                            .frame(width: 30, height: 30)
                    }
                    .buttonStyle(PillIconButtonStyle())
                    .help("Остановить запись")
                }

                if let onCancel {
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
        .padding(.horizontal, showsControls ? 16 : 24)
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
