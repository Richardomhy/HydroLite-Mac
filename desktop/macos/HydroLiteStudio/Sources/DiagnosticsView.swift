import SwiftUI

struct DiagnosticsView: View {
    let message: String
    var body: some View {
        ScrollView { Text(message).textSelection(.enabled).padding() }
    }
}
