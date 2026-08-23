using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.Descriptors;

public sealed class BaseReplayPlayerState : ExportGroupDescriptor<BaseReplayPlayerState>
{
    public override string Path => "/Game/GameModes/Common/BaseReplayPlayerState.BaseReplayPlayerState_C";
    public override ExportCategory Categories => ExportCategory.Movement;
    public override ExportGroupKind Kind => ExportGroupKind.Unknown;

    public uint RemoteRole { get; set; }
    public uint Owner { get; set; }
    public bool OnlySpectator { get; set; }
    public ValorantRawPayload? AllPlayersObfuscatedPlayerInformation { get; set; }
    public ValorantRawPayload? SubjectUniqueId { get; set; }
    public bool IsAfk { get; set; }
    public byte ConnectionStatus { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.RemoteRole).ObjectNetGuid();
        AddProperty(x => x.Owner).ObjectNetGuid();
        AddProperty("bOnlySpectator", x => x.OnlySpectator).Bool();
        AddProperty(x => x.AllPlayersObfuscatedPlayerInformation)
            .Decode(ValorantPayloadDecoders.RawPayload("TArray<FObfuscatedPlayerInformation>"));
        AddProperty(x => x.SubjectUniqueId)
            .Decode(ValorantPayloadDecoders.RawPayload("FUniqueNetIdRepl"));
        AddProperty("bIsAfk", x => x.IsAfk).Bool();
        AddProperty(x => x.ConnectionStatus).EnumByte();
    }
}
