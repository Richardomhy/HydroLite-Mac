import SwiftUI

struct LaunchView: View {
    @ObservedObject var backend: BackendManager

    var body: some View {
        VStack(spacing: 18) {
            Text("HydroLite Studio").font(.largeTitle)
            Text("0.7.0-dev").foregroundStyle(.secondary)
            ProgressView().controlSize(.large)
            Text(backend.status)
            if !backend.errorMessage.isEmpty {
                Text(backend.errorMessage).foregroundStyle(.red).multilineTextAlignment(.center)
                HStack {
                    Button("重试") { backend.restart() }
                    Button("打开日志") { backend.openLogsFolder() }
                }
            }
            Text("数据保存在本机。QGIS、HEC-HMS 和连接器均为可选外部能力。")
                .font(.footnote).foregroundStyle(.secondary)
        }
        .padding(40)
    }
}
