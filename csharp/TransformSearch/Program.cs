using System.Diagnostics;
using System.Globalization;
using TransformSearch;

// The 64-bit lane of every published transform, as this tool's own vocabulary.
// These are what `validate` has to rediscover: a searcher that cannot recover a
// known answer says nothing about an unknown one.
var known = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
{
    ["12.10"] = "rotr8,swap,sub6,rotr5,xornot4,swap",
    ["12.11"] = "rotr8,swap,add6,reverse,sub4,sub3,sub2,swap",
    ["13.00"] = "add8,reverse,add6,xor3,sbox,rotr1",
    ["13.01"] = "not,swap,xornot5,rotr4,not,add1",
    ["13.02"] = "sbox,reverse,sub6,not,reverse,rotl3,rotr2",
};

var mode = args.Length > 0 ? args[0] : "help";
var options = ParseOptions(args);

switch (mode)
{
    case "validate":
    case "search":
        RunSearch();
        break;
    case "emit":
        Emit();
        break;
    case "refine":
        Refine();
        break;
    default:
        Console.WriteLine(
            """
            transform-search -- derive a Valorant payload transform's 64-bit lane.

              validate --corpus <jsonl> --expect <build>   recover a known answer
              search   --corpus <jsonl>                    hunt an unknown one
              emit     --corpus <jsonl> --sequence <ops>   print decoded first blocks

            Options:
              --depth N        maximum composition length (default 7)
              --min-depth N    shortest composition to score (default 3)
              --stage-n N      payloads scored at every node (default 24)
              --rank-n N       payloads used to rank survivors (default 40000)
              --max-k N        largest rotr32(state, k) operand (default 8)
              --loose          allow an operand k to repeat the previous one
              --threads N      degree of parallelism (default: processor count)
              --top N          survivors to print (default 20)
              --shortlist N    behaviours re-ranked over the full corpus (default 4000)
              --known FILE     known plaintext blocks, one hex per line, as the ranking oracle
              --count N        rows for emit (default 200)

            The vocabulary, the descending-operand prior and the scoring mask are
            explained in Ops.cs, Search.cs and Fingerprint.cs. What calibrates
            them is docs/payload-transform-13-04.md.
            """);
        break;
}

return;

void RunSearch()
{
    var path = Require("corpus");
    var depth = OptionInt("depth", 7);
    var minDepth = OptionInt("min-depth", 3);
    var stageN = OptionInt("stage-n", 24);
    var rankN = OptionInt("rank-n", 40_000);
    var maxK = OptionInt("max-k", Ops.MaxK);
    var top = OptionInt("top", 20);
    var threads = OptionInt("threads", Environment.ProcessorCount);
    var strict = !options.ContainsKey("loose");

    var loaded = Stopwatch.StartNew();
    var full = Corpus.Load(path, rankN);
    loaded.Stop();
    Console.WriteLine(
        $"corpus  {full.Count:N0} distinct first blocks from {full.LinesRead:N0} lines "
        + $"({loaded.ElapsedMilliseconds:N0} ms)");

    var stage = full.Take(stageN);
    var threshold = Fingerprint.Threshold(stage.Count);
    Console.WriteLine(
        $"stage   {stage.Count} payloads, threshold {threshold} "
        + $"(a correct decode scores about {Fingerprint.MeanCorrect * stage.Count:N0}, "
        + $"a wrong one about {Fingerprint.MeanRandom * stage.Count:N0})");
    Console.WriteLine(
        $"space   depth <= {depth}, operands k <= {maxK}, "
        + $"{(strict ? "strictly descending" : "non-ascending (loose)")}, {threads} threads");

    var clock = Stopwatch.StartNew();
    var report = new Search(stage, depth, minDepth, threshold, strict, maxK).Run(threads);
    clock.Stop();

    Console.WriteLine(
        $"walked  {report.NodesVisited:N0} compositions in {clock.Elapsed.TotalSeconds:N1} s "
        + $"({report.NodesVisited / Math.Max(clock.Elapsed.TotalSeconds, 0.001) / 1e6:N1}M/s)");
    Console.WriteLine($"passed  {report.Survivors.Count:N0} the stage filter");
    if (report.Overflowed)
    {
        Console.WriteLine(
            $"        {report.OverflowCount:N0} worse ones were evicted to stay inside the per-thread bound");
    }

    if (report.Survivors.Count == 0)
    {
        Console.WriteLine(
            "\nNothing passed. The composition is longer than the depth searched, uses an operand "
            + "outside k <= " + maxK + ", repeats an operand (try --loose), or is built from an "
            + "operation this vocabulary does not have.");
        return;
    }

    // Collapse compositions that behave identically -- different spellings of
    // one function are one answer, and the shortest spelling is the one to
    // report. Grouping on what they *do* rather than on what they are written
    // as is what stops the top of the table being twenty copies of one hit.
    var behaviours = new Dictionary<string, Candidate>();
    foreach (var candidate in report.Survivors)
    {
        var decoded = Search.Decode(candidate, stage);
        var key = string.Join(",", decoded.Select(v => v.ToString("X16", CultureInfo.InvariantCulture)));
        if (!behaviours.TryGetValue(key, out var held) || candidate.Depth < held.Depth)
        {
            behaviours[key] = candidate;
        }
    }

    Console.WriteLine($"        {behaviours.Count:N0} distinct behaviours among them");

    // Rescoring every behaviour over the full corpus costs more than the search
    // itself once the survivor list runs to six figures, and it buys nothing:
    // the stage score already separates the two populations by many sigma, so
    // anything outside its top few thousand is not a contender. The shortlist
    // is reported rather than assumed, so a run can be repeated with a wider
    // one if the leader ever sits near its edge.
    var shortlist = OptionInt("shortlist", 4000);
    var contenders = behaviours.Values.OrderBy(c => c.StageScore).Take(shortlist).ToList();
    if (behaviours.Count > shortlist)
    {
        Console.WriteLine(
            $"        ranking the best {contenders.Count:N0} of them over {full.Count:N0} payloads"
            + $" (--shortlist to widen)");
    }

    // A known-plaintext oracle outranks the bias score whenever one is given:
    // a transform published for a different build scores exactly zero against
    // it, where the bias score only puts it a few sigma away.
    var oracle = options.TryGetValue("known", out var knownPath) && knownPath.Length > 0
        ? KnownPlaintext.Load(knownPath)
        : null;
    if (oracle is not null)
    {
        Console.WriteLine($"known   {oracle.Count:N0} plaintext blocks from builds that are already solved");
    }

    var ranked = contenders
        .AsParallel()
        .WithDegreeOfParallelism(threads)
        .Select(c =>
        {
            var decoded = Search.Decode(c, full);
            return new
            {
                Candidate = c,
                Score = Fingerprint.Score(decoded, full.Count) / (double)full.Count,
                Chain = decoded.Count(Framing.OpensAsChain) / (double)full.Count,
                Known = oracle is null ? 0.0 : oracle.Hits(decoded) / (double)full.Count,
            };
        })
        .OrderByDescending(r => r.Known)
        .ThenBy(r => r.Score)
        .Take(top)
        .ToList();

    Console.WriteLine(
        $"\n{"rank",4} {"known plain",12} {"bits/payload",13} {"as chain",9}  composition"
        + $"\n{"",4} {"(6% right,",12} {"(3.6 right,",13} {"(66% right,",9}"
        + $"\n{"",4} {"0% wrong)",12} {"10.5 wrong)",13} {"9% wrong)",9}");
    for (var i = 0; i < ranked.Count; i++)
    {
        var r = ranked[i];
        Console.WriteLine(
            $"{i + 1,4} {r.Known,12:P2} {r.Score,13:N3} {r.Chain,8:P1}  {r.Candidate.Describe()}");
    }

    if (options.TryGetValue("expect", out var build))
    {
        var wanted = known[build];
        var target = Parse(wanted);
        var targetDecoded = Search.Decode(target, stage);
        var targetKey = string.Join(",", targetDecoded.Select(v => v.ToString("X16", CultureInfo.InvariantCulture)));

        var all = contenders
            .AsParallel()
            .WithDegreeOfParallelism(threads)
            .Select(c => new { Candidate = c, Score = Search.Rescore(c, full) })
            .OrderBy(r => r.Score)
            .ToList();
        var position = all.FindIndex(r =>
        {
            var decoded = Search.Decode(r.Candidate, stage);
            return string.Join(",", decoded.Select(v => v.ToString("X16", CultureInfo.InvariantCulture))) == targetKey;
        });

        Console.WriteLine($"\nexpected {build}: {wanted}");
        Console.WriteLine(
            position < 0
                ? $"  NOT FOUND among the {contenders.Count:N0} ranked (of {behaviours.Count:N0} behaviours)."
                  + " A searcher that cannot recover a known answer proves nothing about an unknown one."
                : $"  recovered at rank {position + 1} of {all.Count} ranked behaviours"
                  + $" as: {all[position].Candidate.Describe()}");
    }
}

/// <summary>
/// Hill-climb one composition toward a higher known-plaintext hit rate.
///
/// Once an oracle exists that a wrong answer scores exactly zero against, a
/// blind walk of the whole space is the wrong tool: a partially-correct
/// composition can be improved one edit at a time and checked outright. This
/// takes every single-edit neighbour -- substitute an operation, insert one,
/// drop one -- and keeps the best, until nothing improves.
///
/// It deliberately ignores the descending-operand prior that bounds the blind
/// search. That prior is what makes enumeration affordable, and it holds for
/// all five published builds, but it is still a prior; a climb that is free to
/// break it is the check on whether the build being solved obeys it.
/// </summary>
void Refine()
{
    var path = Require("corpus");
    var oracle = KnownPlaintext.Load(Require("known"));
    var rankN = OptionInt("rank-n", 20_000);
    var threads = OptionInt("threads", Environment.ProcessorCount);
    var maxK = OptionInt("max-k", Ops.MaxK);
    var corpus = Corpus.Load(path, rankN);
    var current = Parse(Require("sequence"));

    Console.WriteLine($"corpus  {corpus.Count:N0} distinct first blocks");
    Console.WriteLine($"known   {oracle.Count:N0} plaintext blocks");
    Console.WriteLine($"target  a correct decode recognises about 10% of its payloads; a wrong one 0%\n");

    var vocabulary = new List<(int Kind, int K)>();
    for (var kind = 0; kind < Ops.KindCount; kind++)
    {
        if (kind < Ops.FirstOperandKind)
        {
            vocabulary.Add((kind, 0));
            continue;
        }

        for (var k = 1; k <= maxK; k++)
        {
            vocabulary.Add((kind, k));
        }
    }

    double Rate(Candidate c) => oracle.Hits(Search.Decode(c, corpus)) / (double)corpus.Count;

    var best = Rate(current);
    Console.WriteLine($"{best,8:P2}  {current.Describe()}");

    for (var round = 1; ; round++)
    {
        var neighbours = new List<Candidate>();
        var depth = current.Depth;

        for (var i = 0; i < depth; i++)
        {
            foreach (var (kind, k) in vocabulary)
            {
                if (current.Kinds[i] == kind && current.Ks[i] == k)
                {
                    continue;
                }

                var kinds = (int[])current.Kinds.Clone();
                var ks = (int[])current.Ks.Clone();
                kinds[i] = kind;
                ks[i] = k;
                neighbours.Add(new Candidate(kinds, ks, 0));
            }
        }

        for (var i = 0; i <= depth; i++)
        {
            foreach (var (kind, k) in vocabulary)
            {
                neighbours.Add(new Candidate(
                    [.. current.Kinds[..i], kind, .. current.Kinds[i..]],
                    [.. current.Ks[..i], k, .. current.Ks[i..]],
                    0));
            }
        }

        for (var i = 0; i < depth; i++)
        {
            neighbours.Add(new Candidate(
                [.. current.Kinds[..i], .. current.Kinds[(i + 1)..]],
                [.. current.Ks[..i], .. current.Ks[(i + 1)..]],
                0));
        }

        var scored = neighbours
            .AsParallel()
            .WithDegreeOfParallelism(threads)
            .Select(c => new { Candidate = c, Rate = Rate(c) })
            .OrderByDescending(r => r.Rate)
            .First();

        if (scored.Rate <= best)
        {
            Console.WriteLine(
                $"\nno single edit improves on this ({neighbours.Count:N0} tried in round {round});"
                + " it is a local maximum.");
            break;
        }

        best = scored.Rate;
        current = scored.Candidate;
        Console.WriteLine($"{best,8:P2}  {current.Describe()}");
    }

    var decoded = Search.Decode(current, corpus);
    Console.WriteLine($"\nfinal   {current.Describe()}");
    Console.WriteLine($"        as a spec: {Spec(current)}");
    Console.WriteLine($"        known plaintext {best:P2}, opens as chain "
        + $"{decoded.Count(Framing.OpensAsChain) / (double)decoded.Length:P1}, "
        + $"bias {Fingerprint.Score(decoded, decoded.Length) / (double)decoded.Length:N3} bits/payload");
}

string Spec(Candidate c) =>
    string.Join(",", Enumerable.Range(0, c.Depth).Select(i => c.Kinds[i] switch
    {
        Ops.Swap => "swap",
        Ops.Reverse => "reverse",
        Ops.Sbox => "sbox",
        Ops.Not => "not",
        Ops.Add => $"add{c.Ks[i]}",
        Ops.Sub => $"sub{c.Ks[i]}",
        Ops.Xor => $"xor{c.Ks[i]}",
        Ops.XorNot => $"xornot{c.Ks[i]}",
        Ops.RotR => $"rotr{c.Ks[i]}",
        Ops.RotL => $"rotl{c.Ks[i]}",
        _ => "?",
    }));

void Emit()
{
    var path = Require("corpus");
    var count = OptionInt("count", 200);
    var sequence = options.TryGetValue("sequence", out var spec)
        ? spec
        : known[Require("expect")];

    var corpus = Corpus.Load(path, count);
    var decoded = Search.Decode(Parse(sequence), corpus);
    for (var i = 0; i < corpus.Count; i++)
    {
        Console.WriteLine(
            corpus.Values[i].ToString("X16", CultureInfo.InvariantCulture)
            + " " + decoded[i].ToString("X16", CultureInfo.InvariantCulture));
    }
}

Candidate Parse(string spec)
{
    var kinds = new List<int>();
    var ks = new List<int>();
    foreach (var raw in spec.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
    {
        var letters = new string([.. raw.TakeWhile(char.IsLetter)]);
        var digits = raw[letters.Length..];
        var kind = letters.ToLowerInvariant() switch
        {
            "swap" => Ops.Swap,
            "reverse" => Ops.Reverse,
            "sbox" => Ops.Sbox,
            "not" => Ops.Not,
            "add" => Ops.Add,
            "sub" => Ops.Sub,
            "xor" => Ops.Xor,
            "xornot" => Ops.XorNot,
            "rotr" => Ops.RotR,
            "rotl" => Ops.RotL,
            _ => throw new ArgumentException($"unknown operation '{raw}'"),
        };
        kinds.Add(kind);
        ks.Add(digits.Length == 0 ? 0 : int.Parse(digits, CultureInfo.InvariantCulture));
    }

    return new Candidate([.. kinds], [.. ks], 0);
}


Dictionary<string, string> ParseOptions(string[] argv)
{
    var parsed = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    for (var i = 1; i < argv.Length; i++)
    {
        if (!argv[i].StartsWith("--", StringComparison.Ordinal))
        {
            continue;
        }

        var name = argv[i][2..];
        var hasValue = i + 1 < argv.Length && !argv[i + 1].StartsWith("--", StringComparison.Ordinal);
        parsed[name] = hasValue ? argv[++i] : "";
    }

    return parsed;
}

string Require(string name) =>
    options.TryGetValue(name, out var value) && value.Length > 0
        ? value
        : throw new ArgumentException($"--{name} is required");

int OptionInt(string name, int fallback) =>
    options.TryGetValue(name, out var value) && value.Length > 0
        ? int.Parse(value, CultureInfo.InvariantCulture)
        : fallback;
