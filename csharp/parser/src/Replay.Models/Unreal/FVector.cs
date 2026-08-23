namespace Replay.Models.Unreal;

public readonly record struct FVector(double X, double Y, double Z)
{
    public int Bits { get; init; }

    public int ScaleFactor { get; init; }
}