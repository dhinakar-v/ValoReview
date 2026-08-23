using Replay.Encoding.Archives;
using Replay.Models.Descriptors;

namespace Replay.Unreal.Parsing;

public interface IFieldDecoder : IFieldDecoderDescriptor
{
    DecodedFieldValue Decode(ref FieldDecodeContext context, FBitArchive archive);
}