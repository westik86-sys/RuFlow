import Foundation

struct UserDictionaryEntry: Codable, Equatable, Identifiable {
    var id: UUID
    var source: String
    var replacement: String

    init(id: UUID = UUID(), source: String = "", replacement: String = "") {
        self.id = id
        self.source = source
        self.replacement = replacement
    }
}

enum UserDictionary {
    static let enabledKey = "UserDictionaryEnabled"
    static let entriesKey = "UserDictionaryEntries"
    static let defaultIsEnabled = true

    private static let separatorPattern = #"(?:\s+|\s*[-—]\s*)"#
    private static let leadingBoundary = #"(?<![\p{L}\p{N}_])"#
    private static let trailingBoundary = #"(?![\p{L}\p{N}_])"#

    static var isEnabled: Bool {
        get {
            guard UserDefaults.standard.object(forKey: enabledKey) != nil else {
                return defaultIsEnabled
            }

            return UserDefaults.standard.bool(forKey: enabledKey)
        }
        set {
            UserDefaults.standard.set(newValue, forKey: enabledKey)
        }
    }

    static var entries: [UserDictionaryEntry] {
        get {
            guard let data = UserDefaults.standard.data(forKey: entriesKey) else {
                return []
            }

            return (try? JSONDecoder().decode([UserDictionaryEntry].self, from: data)) ?? []
        }
        set {
            guard let data = try? JSONEncoder().encode(newValue) else {
                return
            }

            UserDefaults.standard.set(data, forKey: entriesKey)
        }
    }

    static func apply(to text: String) -> String {
        guard isEnabled else {
            return text
        }

        return entries.reduce(text) { partialText, entry in
            apply(entry: entry, to: partialText)
        }
    }

    private static func apply(entry: UserDictionaryEntry, to text: String) -> String {
        let source = entry.source.trimmingCharacters(in: .whitespacesAndNewlines)
        let replacement = entry.replacement.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !source.isEmpty, !replacement.isEmpty else {
            return text
        }

        let pattern = pattern(for: source)

        do {
            let expression = try NSRegularExpression(pattern: pattern, options: [.caseInsensitive])
            let range = NSRange(text.startIndex..<text.endIndex, in: text)
            return expression.stringByReplacingMatches(
                in: text,
                range: range,
                withTemplate: NSRegularExpression.escapedTemplate(for: replacement)
            )
        } catch {
            return text
        }
    }

    private static func pattern(for source: String) -> String {
        let separators = CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: "-—"))
        let tokens = source
            .components(separatedBy: separators)
            .filter { !$0.isEmpty }
            .map { NSRegularExpression.escapedPattern(for: $0) }

        guard !tokens.isEmpty else {
            return NSRegularExpression.escapedPattern(for: source)
        }

        return leadingBoundary + tokens.joined(separator: separatorPattern) + trailingBoundary
    }
}
