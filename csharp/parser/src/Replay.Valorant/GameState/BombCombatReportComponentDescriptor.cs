using Replay.Models.Descriptors;
using Replay.Models.Unreal;
using Replay.Unreal.Parsing;
using Replay.Valorant.Descriptors;

namespace Replay.Valorant.GameState;

public sealed class BombCombatReportComponentDescriptor : ExportGroupDescriptor<BombCombatReportComponentDescriptor>
{
    public override string Path => "/Game/GameModes/Bomb/Bomb_CombatReportComponent.Bomb_CombatReportComponent_C";
    public override ExportCategory Categories => ExportCategory.GameState | ExportCategory.Gunplay;
    public override ExportGroupKind Kind => ExportGroupKind.Component;

    public ValorantRawPayload? Rounds { get; set; }
    public int RoundNum { get; set; }
    public ValorantRawPayload? Reports { get; set; }
    public int RoundNumber { get; set; }
    public float StateRemainingTime { get; set; }
    public float GameTime { get; set; }
    public byte GamePhase { get; set; }
    public ValorantRawPayload? Interactions { get; set; }
    public string? ParticipantSubject { get; set; }
    public string? ParticipantTeamName { get; set; }
    public uint ParticipantCharacterIcon { get; set; }
    public float DamageDealt { get; set; }
    public int HitsDealt { get; set; }
    public float DamageRecieved { get; set; }
    public int HitsRecieved { get; set; }
    public bool DidKill { get; set; }
    public byte AssistType { get; set; }
    public uint ParticipantsKillerState { get; set; }
    public bool WasKiller { get; set; }
    public ValorantRawPayload? DealtIteractions { get; set; }
    public uint DamageType { get; set; }
    public ValorantRawPayload? RegionalDamageInteractions { get; set; }
    public byte Region { get; set; }
    public int Hits { get; set; }
    public float Damage { get; set; }
    public bool IsWallPen { get; set; }
    public bool IsKill { get; set; }
    public uint DestroyedArmor { get; set; }
    public ValorantRawPayload? ReceivedInteractions { get; set; }
    public int CombatReportIndex { get; set; }
    public uint ResurrectorPlayerState { get; set; }
    public bool Died { get; set; }
    public FVector? DeathLocation { get; set; }

    protected override void Configure()
    {
        AddProperty(x => x.Rounds).Decode(ValorantPayloadDecoders.RawPayload("TArray<FRoundReports>"));
        AddProperty(x => x.RoundNum).Int32();
        AddProperty(x => x.Reports).Decode(ValorantPayloadDecoders.RawPayload("TArray<FCharacterCombatReport>"));
        AddProperty(x => x.RoundNumber).Int32();
        AddProperty(x => x.StateRemainingTime).Float();
        AddProperty(x => x.GameTime).Float();
        AddProperty(x => x.GamePhase).EnumByte();
        AddProperty(x => x.Interactions).Decode(ValorantPayloadDecoders.RawPayload("TArray<FParticipantInteractions>"));
        AddProperty(x => x.ParticipantSubject).FString();
        AddProperty(x => x.ParticipantTeamName).FName();
        AddProperty(x => x.ParticipantCharacterIcon).ObjectNetGuid();
        AddProperty(x => x.DamageDealt).Float();
        AddProperty(x => x.HitsDealt).Int32();
        AddProperty(x => x.DamageRecieved).Float();
        AddProperty(x => x.HitsRecieved).Int32();
        AddProperty("bDidKill", x => x.DidKill).Bool();
        AddProperty(x => x.AssistType).EnumByte();
        AddProperty(x => x.ParticipantsKillerState).ObjectNetGuid();
        AddProperty("bWasKiller", x => x.WasKiller).Bool();
        AddProperty(x => x.DealtIteractions).Decode(ValorantPayloadDecoders.RawPayload("TArray<FCombatInteraction>"));
        AddProperty(x => x.DamageType).ObjectNetGuid();
        AddProperty(x => x.RegionalDamageInteractions)
            .Decode(ValorantPayloadDecoders.RawPayload("TArray<FRegionalDamageInteraction>"));
        AddProperty(x => x.Region).EnumByte();
        AddProperty(x => x.Hits).Int32();
        AddProperty(x => x.Damage).Float();
        AddProperty("bIsWallPen", x => x.IsWallPen).Bool();
        AddProperty("bIsKill", x => x.IsKill).Bool();
        AddProperty(x => x.DestroyedArmor).ObjectNetGuid();
        AddProperty(x => x.ReceivedInteractions).Decode(ValorantPayloadDecoders.RawPayload("TArray<FCombatInteraction>"));
        AddProperty(x => x.CombatReportIndex).Int32();
        AddProperty(x => x.ResurrectorPlayerState).ObjectNetGuid();
        AddProperty("bDied", x => x.Died).Bool();
        AddProperty(x => x.DeathLocation).FVector();
    }
}