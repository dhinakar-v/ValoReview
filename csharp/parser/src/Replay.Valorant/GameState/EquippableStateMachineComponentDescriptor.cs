using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;
using Replay.Valorant.Descriptors;

namespace Replay.Valorant.GameState;

public sealed class EquippableStateMachineComponentDescriptor
    : ExportGroupDescriptor<EquippableStateMachineComponentDescriptor>
{
    public override string Path => "/Script/ShooterGame.EquippableStateMachineComponent";
    public override ExportCategory Categories => ExportCategory.Inventory | ExportCategory.Gunplay;
    public override ExportGroupKind Kind => ExportGroupKind.Component;

    public uint CurrentState { get; set; }
    public ValorantRawPayload? TransitionContext { get; set; }
    public float AuthStartWorldTime { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.CurrentState).ObjectNetGuid();
        AddProperty(x => x.TransitionContext).Decode(ValorantPayloadDecoders.RawPayload("UTransitionContext"));
        AddProperty(x => x.AuthStartWorldTime).Float();
    }
}