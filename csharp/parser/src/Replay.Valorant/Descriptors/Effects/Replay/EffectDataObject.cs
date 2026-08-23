using Replay.Models.Descriptors;
using Replay.Models.Unreal;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.Descriptors.Effects.Replay;

public sealed class EffectDataObject : ExportGroupDescriptor<EffectDataObject>
{
    public FGameplayTag? Name { get; set; }
    public uint? Object { get; set; }

    protected override void Configure()
    {
        AddPropertyHandle(15, "58", x => x.Name, ExportCategory.Gunplay).FGameplayTag();
        AddPropertyHandle(16, "100", x => x.Object, ExportCategory.Gunplay).ObjectNetGuid();
    }
}
