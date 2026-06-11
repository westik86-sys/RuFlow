import SwiftUI

struct FloatingPillView: View {
    let message: String

    var body: some View {
        Text(message)
            .font(.system(size: 16, weight: .semibold))
            .foregroundStyle(.white)
            .lineLimit(1)
            .minimumScaleFactor(0.85)
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
}
