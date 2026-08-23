using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

public sealed class ChildRegionDamageSectionComponentDescriptor
    : ExportGroupDescriptor<ChildRegionDamageSectionComponentDescriptor>
{
    public override string Path => "/Script/ShooterGame.ChildRegionDamageSectionComponent";
    public override ExportCategory Categories => ExportCategory.Gunplay;
    public override ExportGroupKind Kind => ExportGroupKind.Component;

    public bool Alive { get; set; }

    protected override void Configure()
    {
        AddProperty("bAlive", x => x.Alive).Bool();
    }
}