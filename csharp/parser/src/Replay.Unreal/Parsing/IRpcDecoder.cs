using Replay.Encoding.Archives;
using Replay.Models.Descriptors;
using Replay.Models.Events;

namespace Replay.Unreal.Parsing;

public interface IRpcDecoder : IRpcDecoderDescriptor
{
    DecodedPayloadResult Decode(ref FieldDecodeContext context, FBitArchive archive);
}