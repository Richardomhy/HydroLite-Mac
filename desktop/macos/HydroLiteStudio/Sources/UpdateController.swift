import Foundation
import AppKit
import Sparkle

@MainActor
final class UpdateController: ObservableObject {
    @Published var status = "framework_integrated_signing_key_missing"
    private let updaterController: SPUStandardUpdaterController?

    init() {
        let publicKey = Bundle.main.object(forInfoDictionaryKey: "SUPublicEDKey") as? String
        if publicKey?.isEmpty == false {
            updaterController = SPUStandardUpdaterController(
                startingUpdater: true,
                updaterDelegate: nil,
                userDriverDelegate: nil
            )
            status = "available"
        } else {
            updaterController = nil
        }
    }

    func check() {
        if let updaterController {
            updaterController.checkForUpdates(nil)
            return
        }
        let alert = NSAlert()
        alert.messageText = "更新签名尚未配置"
        alert.informativeText = "Sparkle Framework 与 HTTPS Feed 已接入，但正式更新需要在打包时注入 Sparkle EdDSA 公钥。私钥不得进入仓库。"
        alert.runModal()
    }
}
