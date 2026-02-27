// swift-tools-version: 5.9
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "MultiCamCommon",
    platforms: [
        .iOS(.v15),
        .macOS(.v13)
    ],
    products: [
        .library(
            name: "MultiCamCommon",
            targets: ["MultiCamCommon"]),
    ],
    targets: [
        .target(
            name: "MultiCamCommon",
            dependencies: []),
        .testTarget(
            name: "MultiCamCommonTests",
            dependencies: ["MultiCamCommon"]),
    ]
)
