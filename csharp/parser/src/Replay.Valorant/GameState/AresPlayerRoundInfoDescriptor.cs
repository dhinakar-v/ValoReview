using Replay.Models.Descriptors;
using Replay.Unreal.Parsing;

namespace Replay.Valorant.GameState;

/// <summary>
/// One element of OwnerExclusivePlayerInfo's RoundInfos array.
///
/// The two figures are read at a <em>round boundary</em> rather than at a round's
/// start or its end, and that is a measurement rather than a reading of the name:
/// element i is what the player carried into round i + 2, so element 0 is the money
/// round 1 paid out.  On a 21-round capture element 11 is 800 for all ten players,
/// which is the halftime reset entering round 13, and splitting element 0 by an
/// independently inferred round-1 winner gives 3000-plus to the winners and 1900-plus
/// to the losers.  Naming these EndOfRound* or StartOfRound* would be a claim that
/// measurement refutes either way.
///
/// Handles 40, 41 and 42 are deliberately not declared.  40 carries the element's own
/// round number, which is the array index restated; 41 and 42 are the pair a fork of
/// this parser calls StartOfRoundMoney and StartOfRoundLoadoutValue, and they are zero
/// in all 4,030 records measured across 12.10, 12.11 and 13.00.  An undeclared handle
/// is skipped by its own bit count in DynamicArrayDecoder.DecodeElement, so leaving
/// them out costs nothing and states less.
/// </summary>
public sealed class AresPlayerRoundInfoDescriptor : ExportGroupDescriptor<AresPlayerRoundInfoDescriptor>
{
    public override ExportCategory Categories => ExportCategory.GameState | ExportCategory.Economy;

    public int? CreditsAtRoundBoundary { get; set; }
    public int? LoadoutValueAtRoundBoundary { get; set; }

    protected override void Configure()
    {
        AddPropertyHandle(43, x => x.CreditsAtRoundBoundary).Int32();
        AddPropertyHandle(44, x => x.LoadoutValueAtRoundBoundary).Int32();
    }
}
