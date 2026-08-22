using System.Text.Json;
using Replay.Encoding.Archives;
using Replay.Models.Descriptors;
using Replay.Models.Events;
using Replay.Models.Unreal;
using Replay.Valorant;
using Replay.Valorant.Movement;

namespace VrfPositions;

/// <summary>
/// Decode one .vrf into the compact fact file libraries/vrfview/csharpdecode.py reads.
///
/// Usage: vrf-positions [replay.vrf] [out.json] [--hz N]
///
/// Exit codes: 0 decoded, 1 refused (unsupported build, unreadable file), 2 bad
/// arguments.  A refusal prints one sentence to stderr, because the caller turns
/// it into Replay.position_source rather than into an exception.
/// </summary>
internal static class Program
{
    private const int DefaultHz = 10;

    private static int Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.Error.WriteLine("usage: vrf-positions REPLAY.vrf OUT.json [--hz N]");
            return 2;
        }

        var hz = DefaultHz;
        for (var i = 2; i < args.Length - 1; i++)
        {
            if (args[i] == "--hz" && int.TryParse(args[i + 1], out var parsed) && parsed > 0)
            {
                hz = parsed;
            }
        }

        var collector = new Collector(hz);
        try
        {
            using var file = File.OpenRead(args[0]);
            using var archive = new FBinaryArchive(file);
            // Movement only: every other category costs parsing work whose result
            // this emitter would throw away.  ActorSpawned is a channel event
            // rather than an export group, so it survives the filter.
            var profile = new ParseProfile { EnabledCategories = ExportCategory.Movement };
            var reader = ValorantReplayReader.CreateDefault(null, collector, profile);
            reader.Read(archive);
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception.Message);
            return 1;
        }

        using var stream = File.Create(args[1]);
        using var writer = new Utf8JsonWriter(stream);
        collector.Write(writer);
        writer.Flush();
        return 0;
    }
}

/// <summary>
/// Thins movement to the requested rate as it arrives, and remembers every spawn.
///
/// Thinning here rather than in Python is the whole point of this program: a full
/// match is about 3.07 million movement records and roughly 200,000 survive at
/// 10 Hz, so bucketing at the source is what turns gigabytes into megabytes.  The
/// rule is the one vrfview.tracks._drain uses -- bucket by t_ms / period, last
/// record in a bucket wins -- so the thinned result is identical either way.
/// </summary>
internal sealed class Collector : IReplayEventSink
{
    private readonly int _hz;
    private readonly int _periodMs;

    private readonly Dictionary<uint, Dictionary<long, Sample>> _samples = new();
    private readonly Dictionary<uint, string> _archetypes = new();
    private readonly Dictionary<uint, long> _firstSeen = new();
    private readonly Dictionary<uint, FVector> _spawnLocations = new();

    private long _rawMoves;

    public Collector(int hz)
    {
        _hz = hz;
        _periodMs = Math.Max(1, (int)Math.Round(1000.0 / hz));
    }

    public void Emit(ReplayEvent replayEvent)
    {
        switch (replayEvent)
        {
            case RemoteCharacterMovementReceived movement:
                Collect(movement);
                break;
            case ActorSpawned spawned:
                Collect(spawned);
                break;
        }
    }

    private void Collect(RemoteCharacterMovementReceived movement)
    {
        _rawMoves++;
        var actor = movement.ShooterCharacterNetGuidValue;
        var timeMs = (long)Math.Round(movement.TimeSeconds * 1000.0);
        var move = movement.Move;

        if (!_samples.TryGetValue(actor, out var byBucket))
        {
            byBucket = new Dictionary<long, Sample>();
            _samples[actor] = byBucket;
        }

        byBucket[timeMs / _periodMs] = new Sample(
            timeMs,
            move.Position.X,
            move.Position.Y,
            move.Position.Z,
            move.Yaw,
            move.Pitch);
    }

    private void Collect(ActorSpawned spawned)
    {
        var actor = spawned.ActorNetGuid;

        // The full archetype path is split across two fields here, and Python
        // needs it whole: `/Game/Characters/Wushu/Wushu_PC` + `.` +
        // `Default__Wushu_PC_C` is what tracks.codename_for and
        // abilities.spawns_from both parse.
        var path = Join(spawned.ReplicationClassPath, spawned.ArchetypePath);
        if (path.Length > 0 && !_archetypes.ContainsKey(actor))
        {
            _archetypes[actor] = path;
        }

        var timeMs = (long)Math.Round(spawned.TimeSeconds * 1000.0);
        if (!_firstSeen.TryGetValue(actor, out var seen) || timeMs < seen)
        {
            _firstSeen[actor] = timeMs;
        }

        // The spawn transform the Python decoder never had.  Recorded only for
        // the first spawn, because that is the one first_seen names.
        if (spawned.Location is { } location && !_spawnLocations.ContainsKey(actor))
        {
            _spawnLocations[actor] = location;
        }
    }

    private static string Join(string? outer, string? archetype)
    {
        if (string.IsNullOrEmpty(outer))
        {
            return archetype ?? string.Empty;
        }

        return string.IsNullOrEmpty(archetype) ? outer : outer + "." + archetype;
    }

    public void Write(Utf8JsonWriter writer)
    {
        writer.WriteStartObject();
        writer.WriteString("format", "vrf-csharp-decode");
        writer.WriteNumber("version", 1);
        writer.WriteNumber("hz", _hz);
        writer.WriteNumber("moves", _rawMoves);

        writer.WritePropertyName("archetypes");
        writer.WriteStartObject();
        foreach (var pair in _archetypes.OrderBy(entry => entry.Key))
        {
            writer.WriteString(pair.Key.ToString(), pair.Value);
        }

        writer.WriteEndObject();

        writer.WritePropertyName("first_seen");
        writer.WriteStartObject();
        foreach (var pair in _firstSeen.OrderBy(entry => entry.Key))
        {
            writer.WriteNumber(pair.Key.ToString(), pair.Value);
        }

        writer.WriteEndObject();

        writer.WritePropertyName("spawn_locations");
        writer.WriteStartObject();
        foreach (var pair in _spawnLocations.OrderBy(entry => entry.Key))
        {
            writer.WritePropertyName(pair.Key.ToString());
            writer.WriteStartArray();
            writer.WriteNumberValue(pair.Value.X);
            writer.WriteNumberValue(pair.Value.Y);
            writer.WriteNumberValue(pair.Value.Z);
            writer.WriteEndArray();
        }

        writer.WriteEndObject();

        // Columnar, six equal-length arrays per actor -- the shape
        // vrfview.positionfile already stores, and for the same reason.
        writer.WritePropertyName("samples");
        writer.WriteStartObject();
        foreach (var pair in _samples.OrderBy(entry => entry.Key))
        {
            var ordered = pair.Value.OrderBy(entry => entry.Key).Select(entry => entry.Value).ToList();
            writer.WritePropertyName(pair.Key.ToString());
            writer.WriteStartObject();
            WriteLongColumn(writer, "t", ordered);
            WriteColumn(writer, "x", ordered, sample => sample.X);
            WriteColumn(writer, "y", ordered, sample => sample.Y);
            WriteColumn(writer, "z", ordered, sample => sample.Z);
            WriteColumn(writer, "yaw", ordered, sample => sample.Yaw);
            WriteColumn(writer, "pitch", ordered, sample => sample.Pitch);
            writer.WriteEndObject();
        }

        writer.WriteEndObject();

        writer.WriteEndObject();
    }

    private static void WriteLongColumn(Utf8JsonWriter writer, string name, List<Sample> samples)
    {
        writer.WritePropertyName(name);
        writer.WriteStartArray();
        foreach (var sample in samples)
        {
            writer.WriteNumberValue(sample.TimeMs);
        }

        writer.WriteEndArray();
    }

    private static void WriteColumn(
        Utf8JsonWriter writer,
        string name,
        List<Sample> samples,
        Func<Sample, double> select)
    {
        writer.WritePropertyName(name);
        writer.WriteStartArray();
        foreach (var sample in samples)
        {
            writer.WriteNumberValue(select(sample));
        }

        writer.WriteEndArray();
    }

    private readonly record struct Sample(
        long TimeMs,
        double X,
        double Y,
        double Z,
        double Yaw,
        double Pitch);
}
