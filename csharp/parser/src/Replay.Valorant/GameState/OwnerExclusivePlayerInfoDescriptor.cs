using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

/// <summary>
/// Each player's own economy, one array element per round boundary.
///
/// Owner is the player's controller, which is also what BombPlayerState.PlayerInfo
/// points back at, so a caller joins a record to a pawn through that state rather
/// than through this actor.
///
/// The fields are declared by name and not by handle: an actor group's handles come
/// from the replay's own NetFieldExportGroup, so a name survives a layout shift that
/// a handle does not.
/// </summary>
public sealed class OwnerExclusivePlayerInfoDescriptor : ExportGroupDescriptor<OwnerExclusivePlayerInfoDescriptor>
{
    public override string Path => "/Script/ShooterGame.OwnerExclusivePlayerInfo";
    public override ExportCategory Categories => ExportCategory.GameState | ExportCategory.Economy;
    public override ExportGroupKind Kind => ExportGroupKind.Actor;

    public uint Owner { get; set; }
    public AresPlayerRoundInfoDescriptor[]? RoundInfos { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.Owner).ObjectNetGuid();
        AddProperty(x => x.RoundInfos).RepLayoutDynamicArray<AresPlayerRoundInfoDescriptor>();
    }
}
