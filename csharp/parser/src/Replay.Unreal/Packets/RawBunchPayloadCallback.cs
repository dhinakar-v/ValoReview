using Replay.Encoding.Archives;
using Replay.Models.Net;

namespace Replay.Unreal.Packets;

public delegate void RawBunchPayloadCallback(ref RawBunchHeader header, FBitArchive payload);