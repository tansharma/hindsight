// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "PkgA",
    products: [
        .library(name: "Core", targets: ["Core"]),
    ],
    dependencies: [
        .package(path: "../PkgB"),
        .package(url: "https://github.com/Alamofire/Alamofire.git", from: "5.8.0"),
    ],
    targets: [
        .target(
            name: "Core",
            dependencies: [.product(name: "Storage", package: "PkgB")]
        ),
        // Custom source path: the directory is Net, the module is Networking.
        .target(
            name: "Networking",
            dependencies: [
                .target(name: "Core"),
                .product(name: "Alamofire", package: "Alamofire"),
            ],
            path: "Sources/Net"
        ),
        .testTarget(name: "CoreTests", dependencies: ["Core"]),
    ]
)
