import SwiftUI
import AppKit

@main
struct HydroLiteStudioApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var backend = BackendManager()
    @StateObject private var updates = UpdateController()

    var body: some Scene {
        WindowGroup("HydroLite Studio") {
            Group {
                if let url = backend.localURL, backend.isHealthy {
                    WebView(url: url)
                } else {
                    LaunchView(backend: backend)
                }
            }
            .frame(minWidth: 1100, minHeight: 720)
            .onAppear { backend.start() }
            .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in backend.stop() }
        }
        .commands {
            CommandGroup(replacing: .appInfo) {
                Button("About HydroLite Studio") {
                    NSApp.orderFrontStandardAboutPanel(options: [.applicationName: "HydroLite Studio", .applicationVersion: "0.7.0-dev"])
                }
            }
            CommandMenu("HydroLite") {
                Button("New Project") { backend.reload() }
                Button("Open Project Center") { backend.reload() }
                Button("Open Run Center") { backend.reload() }
                Divider()
                Button("Open Data Folder") { backend.openDataFolder() }
                Button("Open Logs") { backend.openLogsFolder() }
                Divider()
                Button("Check for Updates") { updates.check() }
                Button("Reload Interface") { backend.reload() }
                Button("Restart Backend") { backend.restart() }
            }
        }
    }
}
