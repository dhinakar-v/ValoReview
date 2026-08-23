using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

public sealed class AmmoComponentDescriptor : ExportGroupDescriptor<AmmoComponentDescriptor>
{
    public override string Path => "/Script/ShooterGame.AmmoComponent";
    public override ExportCategory Categories => ExportCategory.Inventory | ExportCategory.Gunplay;
    public override ExportGroupKind Kind => ExportGroupKind.Component;

    public int AuthResourceAmount { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.AuthResourceAmount).Int32();
    }
}