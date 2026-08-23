namespace Replay.Models.Unreal;

public readonly record struct FRepMovement(
    FVector? LinearVelocity,
    FVector? AngularVelocity,
    FVector? Location,
    FRotator? Rotation,
    bool bSimulatedPhysicsSleep,
    bool bRepPhysics,
    uint ServerFrame,
    uint ServerPhysicsHandle);
