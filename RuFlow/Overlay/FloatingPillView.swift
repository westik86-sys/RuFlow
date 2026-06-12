import SwiftUI

@MainActor
final class FloatingPillState: ObservableObject {
    @Published var message = ""
    @Published var showsControls = false
    @Published var showsLoader = false
    @Published var showsError = false
    @Published var errorMessage = ""
    @Published var recordingLevel = 0.0

    var onStop: (() -> Void)?
    var onCancel: (() -> Void)?

    func showError(_ message: String) {
        self.message = ""
        errorMessage = message
        showsControls = false
        showsLoader = false
        showsError = true
        recordingLevel = 0
        onStop = nil
        onCancel = nil
    }

    func showLoader() {
        message = ""
        showsControls = false
        showsLoader = true
        showsError = false
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
        showsLoader = false
        showsError = false
    }
}

struct FloatingPillView: View {
    @ObservedObject var state: FloatingPillState
    private let waveformBarHeights: [CGFloat] = [
        6, 12, 8, 14, 26, 20, 32, 26, 30, 18,
        22, 14, 6, 10, 14, 24, 32, 30, 24, 14
    ]

    var body: some View {
        ZStack {
            if state.showsLoader {
                loadingPill
                    .transition(.scale(scale: 0.88).combined(with: .opacity))
            } else if state.showsControls {
                recordingPill
                    .transition(.opacity)
            } else if state.showsError {
                errorPill
                    .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.22), value: state.showsControls)
        .animation(.easeInOut(duration: 0.22), value: state.showsLoader)
        .animation(.easeInOut(duration: 0.22), value: state.showsError)
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

    private var loadingPill: some View {
        LoadingSpinner()
            .frame(width: 24, height: 24)
            .frame(width: 65, height: 65)
            .background(pillBackground(cornerRadius: 24))
            .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 24, style: .continuous)
                    .stroke(Color(red: 248 / 255, green: 248 / 255, blue: 248 / 255).opacity(0.5), lineWidth: 0.5)
            )
    }

    private var errorPill: some View {
        HStack {
            Text(state.errorMessage)
                .font(.system(size: 20, weight: .medium, design: .default))
                .tracking(0.38)
                .foregroundStyle(.white)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
                .frame(width: 342, alignment: .leading)

            Spacer(minLength: 0)
        }
        .padding(.leading, 20)
        .padding(.trailing, 21)
        .frame(width: 383, height: 89, alignment: .leading)
        .background(pillBackground(cornerRadius: 24))
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(Color(red: 248 / 255, green: 248 / 255, blue: 248 / 255).opacity(0.5), lineWidth: 0.5)
        )
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

private struct LoadingSpinner: View {
    @State private var isRotating = false

    var body: some View {
        Circle()
            .trim(from: 0.08, to: 0.8)
            .stroke(
                Color(red: 248 / 255, green: 248 / 255, blue: 248 / 255),
                style: StrokeStyle(lineWidth: 2, lineCap: .round)
            )
            .rotationEffect(.degrees(isRotating ? 360 : 0))
            .animation(.linear(duration: 0.85).repeatForever(autoreverses: false), value: isRotating)
            .onAppear {
                isRotating = true
            }
    }
}
