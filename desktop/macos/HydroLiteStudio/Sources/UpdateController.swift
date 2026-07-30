import Foundation
import AppKit

@MainActor
final class UpdateController: ObservableObject {
    @Published var status = "framework_ready_configuration_missing"

    func check() {
        let alert = NSAlert()
        alert.messageText = "更新源尚未配置"
        alert.informativeText = "当前开发版使用安全的手动 release manifest 检查，不会下载或安装未签名更新。"
        alert.runModal()
    }
}
