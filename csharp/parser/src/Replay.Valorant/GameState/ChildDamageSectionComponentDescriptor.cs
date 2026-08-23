using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

public sealed class ChildDamageSectionComponentDescriptor
    : ExportGroupDescriptor<ChildDamageSectionComponentDescriptor>
{
    public override string Path => "/Script/ShooterGame.ChildDamageSectionComponent";
    public override ExportCategory Categories => ExportCategory.Gunplay;
    public override ExportGroupKind Kind => ExportGroupKind.Component;

    public bool Alive { get; set; }
    public float MaximumLife { get; set; }

    protected override void Configure()
    {
        AddProperty("bAlive", x => x.Alive).Bool();
        AddProperty(x => x.MaximumLife).Float();
    }
}