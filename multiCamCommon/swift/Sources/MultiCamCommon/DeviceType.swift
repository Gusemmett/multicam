import Foundation

/// Device type values used in API responses
public enum DeviceType: String, Codable, CaseIterable {
    /// iOS device (iPhone)
    case iosIPhone = "iOS:iPhone"

    /// Android phone device
    case androidPhone = "Android:Phone"

    /// Android Quest VR headset
    case androidQuest = "Android:Quest"

    /// OAK camera device
    case oak = "Oak"
}
