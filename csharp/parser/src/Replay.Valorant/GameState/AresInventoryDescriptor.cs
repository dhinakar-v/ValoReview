using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;
using Replay.Valorant.Descriptors;

namespace Replay.Valorant.GameState;

public sealed class AresInventoryDescriptor : ExportGroupDescriptor<AresInventoryDescriptor>
{
    public override string Path => "/Script/ShooterGame.AresInventory";
    public override ExportCategory Categories => ExportCategory.Inventory | ExportCategory.Gunplay;
    public override ExportGroupKind Kind => ExportGroupKind.Component;

    public bool IsActive { get; set; }
    public ValorantRawPayload? ItemSlots { get; set; }
    public uint NewCurrentEquippable { get; set; }
    public uint Character { get; set; }
    public float NetTimestamp { get; set; }
    public int RespawnNumber { get; set; }
    public uint CurrentEquippable { get; set; }

    protected override void Configure()
    {
        AddProperty("bIsActive", x => x.IsActive, ExportCategory.Inventory).Bool();
        AddProperty(x => x.ItemSlots, ExportCategory.Inventory).Decode(ValorantPayloadDecoders.RawPayload("UItemSlot*[16]"));
        AddProperty(x => x.NewCurrentEquippable, ExportCategory.Inventory | ExportCategory.Gunplay).ObjectNetGuid();
        AddProperty(x => x.Character, ExportCategory.Inventory | ExportCategory.Gunplay).ObjectNetGuid();
        AddProperty(x => x.NetTimestamp, ExportCategory.Inventory).Float();
        AddProperty(x => x.RespawnNumber, ExportCategory.Inventory).Int32();
        AddProperty(x => x.CurrentEquippable, ExportCategory.Inventory | ExportCategory.Gunplay).ObjectNetGuid();
    }
}
