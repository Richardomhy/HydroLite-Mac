// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "HydroLiteStudio",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "HydroLiteStudio", targets: ["HydroLiteStudio"])],
    targets: [
        .binaryTarget(
            name: "Sparkle",
            path: ".build/vendor/Sparkle.xcframework"
        ),
        .executableTarget(
            name: "HydroLiteStudio",
            dependencies: ["Sparkle"],
            path: ".",
            sources: ["Sources"],
            resources: [.copy("Resources")],
            linkerSettings: [
                .unsafeFlags(["-Xlinker", "-rpath", "-Xlinker", "@executable_path/../Frameworks"])
            ]
        )
    ]
)
