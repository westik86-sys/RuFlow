import SwiftUI

@MainActor
final class FloatingPillState: ObservableObject {
    @Published var message = ""
    @Published var showsControls = false
    @Published var recordingLevel = 0.0

    var onStop: (() -> Void)?
    var onCancel: (() -> Void)?

    func showMessage(_ message: String) {
        self.message = message
        showsControls = false
        recordingLevel = 0
        onStop = nil
        onCancel = nil
    }

    func showRecording(
        message: String,
        level: Double,
        onStop: @escaping () -> Void,
        onCancel: @escaping () -> Void
    ) {
        self.message = message
        recordingLevel = min(max(level, 0), 1)
        self.onStop = onStop
        self.onCancel = onCancel
        showsControls = true
    }
}

struct FloatingPillView: View {
    @ObservedObject var state: FloatingPillState
    private let waveformBarHeights: [CGFloat] = [
        6, 12, 8, 14, 26, 20, 32, 26, 30, 18,
        22, 14, 6, 10, 14, 24, 32, 30, 24, 14
    ]

    var body: some View {
        if state.showsControls {
            recordingPill
        } else {
            messagePill
        }
    }

    private var recordingPill: some View {
        HStack(spacing: 0) {
            HStack(spacing: 3) {
                ForEach(waveformBarHeights.indices, id: \.self) { index in
                    Capsule()
                        .fill(Color(red: 248 / 255, green: 248 / 255, blue: 248 / 255))
                        .frame(width: 3, height: waveformBarHeight(at: index))
                }
            }

            Spacer(minLength: 0)

            Text(state.message)
                .font(.system(size: 20, weight: .bold, design: .rounded))
                .tracking(0.357)
                .foregroundStyle(Color(red: 248 / 255, green: 248 / 255, blue: 248 / 255))
                .lineLimit(1)
        }
        .padding(.leading, 20)
        .padding(.trailing, 21)
        .frame(width: 223, height: 65)
        .background(pillBackground(cornerRadius: 24))
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(Color(red: 248 / 255, green: 248 / 255, blue: 248 / 255).opacity(0.5), lineWidth: 0.5)
        )
        .animation(.easeOut(duration: 0.08), value: state.recordingLevel)
    }

    private var messagePill: some View {
        HStack(spacing: 14) {
            Text(state.message)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.85)
        }
        .padding(.horizontal, 24)
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

    private func pillBackground(cornerRadius: CGFloat) -> some View {
        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
            .fill(.ultraThinMaterial)
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(Color(red: 54 / 255, green: 54 / 255, blue: 54 / 255).opacity(0.7))
            )
    }

    private func waveformBarHeight(at index: Int) -> CGFloat {
        let minimumHeight: CGFloat = 3
        let maximumHeight: CGFloat = 32
        let normalizedHeight = (waveformBarHeights[index] - minimumHeight) / (maximumHeight - minimumHeight)
        let level = CGFloat(state.recordingLevel)
        return minimumHeight + (maximumHeight - minimumHeight) * normalizedHeight * level
    }
}
