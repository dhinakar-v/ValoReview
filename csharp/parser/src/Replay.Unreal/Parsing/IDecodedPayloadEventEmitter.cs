namespace Replay.Unreal.Parsing;

public interface IDecodedPayloadEventEmitter
{
    void EmitDecodedEvents(ref FieldDecodeContext context);
}
