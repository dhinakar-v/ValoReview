using Replay.Models.Descriptors;
using Replay.Models.Unreal;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.Descriptors.Agents.Sprinter;

public sealed class NeonTunnelDescriptor : ExportGroupDescriptor<NeonTunnelDescriptor>
{
    public override string Path =>
        "/Game/Characters/Sprinter/S0/Ability_4/Projectile_Neon_C_Tunnel.Projectile_Neon_C_Tunnel_C";
    public override ExportCategory Categories => ExportCategory.Ability;
    public override ExportGroupKind Kind => ExportGroupKind.Actor;

    public FRepMovement ReplicatedMovement { get; set; }
    public uint Owner { get; set; }
    public uint Instigator { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.ReplicatedMovement)
            .ReplicatedMovement(ERotatorQuantization.ByteComponents);
        AddProperty(x => x.Owner).ObjectNetGuid();
        AddProperty(x => x.Instigator).ObjectNetGuid();
    }
}
