// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "HydroLiteStudio",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "HydroLiteStudio", targets: ["HydroLiteStudio"])],
    targets: [
        .executableTarget(
            name: "HydroLiteStudio",
            path: ".",
            sources: ["Sources"],
            resources: [.copy("Resources")]
        )
    ]
)
