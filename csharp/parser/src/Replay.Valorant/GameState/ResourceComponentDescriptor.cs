using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

public class ResourceComponentDescriptor<TDescriptor> : ExportGroupDescriptor<TDescriptor>
    where TDescriptor : ResourceComponentDescriptor<TDescriptor>
{
    public override ExportCategory Categories => ExportCategory.Ability | ExportCategory.Inventory;
    public override ExportGroupKind Kind => ExportGroupKind.Component;

    public int AuthResourceAmount { get; set; }
    public int PredictedResourceAmount { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.AuthResourceAmount).Int32();
        AddProperty(x => x.PredictedResourceAmount).Int32();
    }
}