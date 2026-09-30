import Foundation
import AppKit

private struct BackendManifest: Decodable {
    let pid: Int32
    let port: Int
    let url: String
}

@MainActor
final class BackendManager: ObservableObject {
    @Published var status = "正在启动本地后端…"
    @Published var errorMessage = ""
    @Published var isHealthy = false
    @Published var localURL: URL?

    private var process: Process?
    private var manifestURL: URL {
        applicationSupport.appendingPathComponent("backend_manifest.json")
    }
    private var applicationSupport: URL {
        if let root = ProcessInfo.processInfo.environment["HYDROLITE_DESKTOP_TEST_ROOT"] {
            return URL(fileURLWithPath: root, isDirectory: true).appendingPathComponent("HydroLite Studio", isDirectory: true)
        }
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/HydroLite Studio", isDirectory: true)
    }
    private var logs: URL {
        if let root = ProcessInfo.processInfo.environment["HYDROLITE_DESKTOP_TEST_ROOT"] {
            return URL(fileURLWithPath: root, isDirectory: true).appendingPathComponent("HydroLite Studio", isDirectory: true)
        }
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/HydroLite Studio", isDirectory: true)
    }

    func start() {
        guard process == nil else { return }
        do {
            try FileManager.default.createDirectory(at: applicationSupport, withIntermediateDirectories: true)
            try FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
            try? FileManager.default.removeItem(at: manifestURL)
            let resources = Bundle.main.resourceURL!
            let executable = resources
                .appendingPathComponent("backend/hydrolite-backend/hydrolite-backend")
            guard FileManager.default.isExecutableFile(atPath: executable.path) else {
                throw NSError(domain: "HydroLite", code: 1, userInfo: [NSLocalizedDescriptionKey: "Backend executable is missing: \(executable.path)"])
            }
            let task = Process()
            task.executableURL = executable
            let runtime = ProcessInfo.processInfo.environment["HYDROLITE_DESKTOP_TEST_ROOT"].map {
                URL(fileURLWithPath: $0, isDirectory: true).appendingPathComponent("runtime").path
            } ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".hydrolite/runtime").path
            task.arguments = ["--port", "0", "--runtime-dir", runtime, "--manifest", manifestURL.path, "--parent-pid", String(ProcessInfo.processInfo.processIdentifier)]
            task.currentDirectoryURL = resources
            let output = logs.appendingPathComponent("backend.stdout.log")
            let errors = logs.appendingPathComponent("backend.stderr.log")
            FileManager.default.createFile(atPath: output.path, contents: nil)
            FileManager.default.createFile(atPath: errors.path, contents: nil)
            task.standardOutput = try FileHandle(forWritingTo: output)
            task.standardError = try FileHandle(forWritingTo: errors)
            try task.run()
            process = task
            Task { await waitForHealth() }
        } catch {
            status = "启动失败"
            errorMessage = error.localizedDescription
        }
    }

    func stop() {
        guard let task = process else { return }
        if task.isRunning {
            task.terminate()
            let deadline = Date().addingTimeInterval(5)
            while task.isRunning && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.05)) }
            if task.isRunning { kill(task.processIdentifier, SIGKILL) }
        }
        process = nil
        isHealthy = false
        try? FileManager.default.removeItem(at: manifestURL)
    }

    func restart() {
        stop()
        status = "正在重新启动…"
        errorMessage = ""
        start()
    }

    func reload() {
        guard let url = localURL else { return }
        localURL = nil
        localURL = url
    }

    func openDataFolder() { NSWorkspace.shared.open(applicationSupport) }
    func openLogsFolder() { NSWorkspace.shared.open(logs) }

    private func waitForHealth() async {
        let deadline = Date().addingTimeInterval(45)
        while Date() < deadline {
            guard process?.isRunning == true else {
                status = "后端已退出"
                errorMessage = "请在日志目录查看 backend.stderr.log"
                return
            }
            if let data = try? Data(contentsOf: manifestURL),
               let manifest = try? JSONDecoder().decode(BackendManifest.self, from: data),
               let url = URL(string: manifest.url) {
                guard manifest.pid == process?.processIdentifier,
                      manifest.port > 0, manifest.port < 65536,
                      url.scheme == "http", url.host == "127.0.0.1",
                      url.port == manifest.port else {
                    status = "后端清单无效"
                    errorMessage = "后端进程标识或 loopback 端口与启动配置不一致。"
                    return
                }
                if await healthy(url: url) {
                    localURL = url
                    isHealthy = true
                    status = "运行中"
                    return
                }
            }
            try? await Task.sleep(for: .milliseconds(250))
        }
        status = "启动超时"
        errorMessage = "后端未在 45 秒内通过健康检查。"
    }

    private func healthy(url: URL) async -> Bool {
        guard url.host == "127.0.0.1" else { return false }
        do {
            let health = url.appendingPathComponent("_stcore/health")
            let (_, response) = try await URLSession.shared.data(from: health)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }
}
