namespace Replay.Valorant.Movement;

public sealed class RemoteCharacterUpdateBatch
{
    private readonly List<RemoteCharacterUpdate> _updates;

    internal RemoteCharacterUpdateBatch(int capacity)
    {
        _updates = capacity > 0 ? new List<RemoteCharacterUpdate>(capacity) : [];
    }

    public IReadOnlyList<RemoteCharacterUpdate> Updates => _updates;

    public int MoveCount
    {
        get
        {
            var count = 0;
            foreach (var update in _updates)
            {
                count += update.ComponentDataStream?.MoveCount ?? 0;
            }

            return count;
        }
    }

    public int MovementParseErrorCount
    {
        get
        {
            var count = 0;
            foreach (var update in _updates)
            {
                if (update.ComponentDataStream?.MovementParseError is not null)
                {
                    count++;
                }
            }

            return count;
        }
    }

    internal void AddUpdate(RemoteCharacterUpdate update) => _updates.Add(update);

    public override string ToString() =>
        $"updates={_updates.Count}, moves={MoveCount}, movementErrors={MovementParseErrorCount}";
}