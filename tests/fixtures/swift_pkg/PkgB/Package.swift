// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "PkgB",
    dependencies: [
        .package(path: "../PkgA"),
        .package(url: "https://github.com/apple/swift-log.git", from: "1.5.0"),
    ],
    targets: [
        .target(name: "Storage", dependencies: [.product(name: "Core", package: "PkgA")]),
        .target(
            name: "Sync",
            dependencies: ["Storage", .product(name: "Logging", package: "swift-log")]
        ),
    ]
)
