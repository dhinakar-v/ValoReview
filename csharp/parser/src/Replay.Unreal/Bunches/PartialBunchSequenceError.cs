namespace Replay.Unreal.Bunches;

internal enum PartialBunchSequenceError
{
    None,
    OverlappingInitial,
    MissingInitial,
    MismatchedContinuation,
}