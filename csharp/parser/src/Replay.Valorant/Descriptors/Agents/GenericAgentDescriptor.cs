using Replay.Models.Descriptors;
using Replay.Models.Unreal;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.Descriptors.Agents;

public abstract class GenericAgentDescriptor : ExportGroupDescriptor<GenericAgentDescriptor>
{
    public override ExportCategory Categories => ExportCategory.Agent;
    public override ExportGroupKind Kind => ExportGroupKind.Actor;

    public bool ReplicateMovement { get; set; }
    public uint Role { get; set; }
    public uint RemoteRole { get; set; }
    public uint Owner { get; set; }
    public uint Instigator { get; set; }
    public uint PlayerState { get; set; }
    public uint Controller { get; set; }
    public float ReplayLastTransformUpdateTimeStamp { get; set; }
    public FVector ReplicatedGravityDirection { get; set; }
    public uint ReplicatedMovementMode { get; set; }
    public bool IsPlayerCharacter { get; set; }
    public bool CrouchHeld { get; set; }

    protected override void Configure()
    {
        AddProperty(x => RemoteRole).Ignore();
        AddProperty(x => Role).Ignore();

        AddProperty("bReplicateMovement", x => ReplicateMovement).Bool();
        AddProperty(x => Owner).ObjectNetGuid();
        AddProperty(x => Instigator).ObjectNetGuid();
        AddProperty(x => PlayerState).ObjectNetGuid();
        AddProperty(x => Controller).ObjectNetGuid();
        AddProperty(x => ReplayLastTransformUpdateTimeStamp).Ignore();
        AddProperty(x => ReplicatedGravityDirection).FVectorNetQuantizeNormal();
        AddProperty(x => ReplicatedMovementMode).Byte();
        AddProperty("bIsPlayerCharacter", x => IsPlayerCharacter).Bool();
        AddProperty("bCrouchHeld", x => CrouchHeld).Bool();
    }
}