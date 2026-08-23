namespace Replay.Models.Descriptors;

public interface IDecodedPayload
{
    IReadOnlySet<string> DecodedProperties { get; }

    bool HasDecoded(string propertyName);
}
