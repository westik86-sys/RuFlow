import SwiftUI

@MainActor
final class FloatingPillState: ObservableObject {
    @Published var message = ""
    @Published var showsControls = false
    @Published var showsLoader = false
    @Published var showsError = false
    @Published var errorMessage = ""
    @Published var waveformLevels = Array(repeating: 0.0, count: 20)

    var onStop: (() -> Void)?
    var onCancel: (() -> Void)?

    func showError(_ message: String) {
        self.message = ""
        errorMessage = message
        showsControls = false
        showsLoader = false
        showsError = true
        resetWaveform()
        onStop = nil
        onCancel = nil
    }

    func showLoader() {
        message = ""
        showsControls = false
        showsLoader = true
        showsError = false
        resetWaveform()
        onStop = nil
        onCancel = nil
    }

    func showRecording(
        message: String,
        level: Double,
        onStop: @escaping () -> Void,
        onCancel: @escaping () -> Void
    ) {
        let boundedLevel = min(max(level, 0), 1)

        if self.message != message {
            self.message = message
        }

        appendWaveformLevel(boundedLevel)

        if self.onStop == nil {
            self.onStop = onStop
        }

        if self.onCancel == nil {
            self.onCancel = onCancel
        }

        if !showsControls {
            showsControls = true
        }

        if showsLoader {
            showsLoader = false
        }

        if showsError {
            showsError = false
        }
    }

    func hide() {
        message = ""
        errorMessage = ""
        showsControls = false
        showsLoader = false
        showsError = false
        resetWaveform()
        onStop = nil
        onCancel = nil
    }

    private func appendWaveformLevel(_ level: Double) {
        let gatedLevel = level < 0.035 ? 0 : level
        let previousLevel = waveformLevels.last ?? 0
        let smoothing = gatedLevel > previousLevel ? 0.72 : 0.24
        let smoothedLevel = previousLevel + (gatedLevel - previousLevel) * smoothing
        let boundedLevel = min(max(smoothedLevel, 0), 1)

        waveformLevels.removeFirst()
        waveformLevels.append(boundedLevel)
    }

    private func resetWaveform() {
        waveformLevels = Array(repeating: 0.0, count: waveformLevels.count)
    }
}

struct FloatingPillView: View {
    @ObservedObject var state: FloatingPillState

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
                ForEach(state.waveformLevels.indices, id: \.self) { index in
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
                .monospacedDigit()
                .frame(width: 50, alignment: .trailing)
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
        .animation(.easeOut(duration: 0.07), value: state.waveformLevels)
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
        let level = CGFloat(state.waveformLevels[index])
        return minimumHeight + (maximumHeight - minimumHeight) * level
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
