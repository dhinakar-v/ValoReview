using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;
using Replay.Valorant.Descriptors;

namespace Replay.Valorant.GameState;

/// <summary>
/// A player's state, minus the three fields that identify the person behind it.
///
/// Subject (a PUUID), CompetitiveTier and UniqueId are replicated and are
/// deliberately not decoded here: this parser feeds a local review tool that has
/// no business writing an account identifier into a cache file or a web response.
/// Dropping them cannot desynchronise anything -- FieldPayloadParser.ParseProperty
/// reads a per-property bit count and skips a property with no binding -- and
/// nothing else in the tree reads them.
/// </summary>
public sealed class BombPlayerStateDescriptor : ExportGroupDescriptor<BombPlayerStateDescriptor>
{
    public override string Path => "/Game/GameModes/Bomb/BombPlayerState.BombPlayerState_C";
    public override ExportCategory Categories => ExportCategory.GameState | ExportCategory.Gunplay;
    public override ExportGroupKind Kind => ExportGroupKind.Actor;

    public int PlayerId { get; set; }
    public uint SpectatedPlayer { get; set; }
    public uint PlayerInfo { get; set; }
    public uint SpawnedCharacter { get; set; }
    public uint PossessedCharacter { get; set; }
    public bool UltimateActive { get; set; }
    public int NumUltimatePoints { get; set; }
    public int TotalAcquiredUltimatePoints { get; set; }

    protected override void Configure()
    {
        AddProperty("PlayerId", x => x.PlayerId, ExportCategory.GameState).Int32();
        AddProperty("PlayerID", x => x.PlayerId, ExportCategory.GameState).Int32();
        AddProperty(x => x.SpectatedPlayer, ExportCategory.GameState).ObjectNetGuid();
        AddProperty(x => x.PlayerInfo, ExportCategory.GameState).ObjectNetGuid();
        AddProperty(x => x.SpawnedCharacter, ExportCategory.GameState | ExportCategory.Gunplay).ObjectNetGuid();
        AddProperty(x => x.PossessedCharacter, ExportCategory.GameState | ExportCategory.Gunplay).ObjectNetGuid();
        AddProperty("bUltimateActive", x => x.UltimateActive, ExportCategory.GameState).Bool();
        AddProperty(x => x.NumUltimatePoints, ExportCategory.GameState).Int32();
        AddProperty(x => x.TotalAcquiredUltimatePoints, ExportCategory.GameState).Int32();
    }
}
