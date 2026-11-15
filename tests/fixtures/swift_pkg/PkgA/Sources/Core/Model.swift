import Foundation
import Storage  // planted: Storage (PkgB) imports Core back

// TODO: split the record type out of Core
public struct Record {
    public let id: UUID
    public init(id: UUID) { self.id = id }
}
