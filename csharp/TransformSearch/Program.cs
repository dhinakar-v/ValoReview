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

// The four keystream constants of every published build, which `constants`
// checks itself against. `tail_xor` is the low byte of `seed_addend` in all
// five, which is a cross-check on a recovered pair and never a licence to
// invent one.
var Published = new Dictionary<string, BuildConstants>(StringComparer.OrdinalIgnoreCase)
{
    ["12.10"] = new(0x12FD0EE5, 0x1B, false, 0xE5),
    ["12.11"] = new(0x409D36A3, 0x23, true, 0xA3),
    ["13.00"] = new(0x2949B6EF, 0x11, false, 0xEF),
    ["13.01"] = new(0xE62FCD5C, 0x24, false, 0x5C),
    ["13.02"] = new(0x9E81A37C, 0x04, false, 0x7C),
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
    case "constants":
        Constants();
        break;
    case "solve":
        SolveConstants();
        break;
    case "lane32":
        Lane32Command();
        break;
    case "lane8":
        Lane8Command();
        break;
    default:
        Console.WriteLine(
            """
            transform-search -- derive a Valorant payload transform's 64-bit lane.

              validate --corpus <jsonl> --expect <build>   recover a known answer
              search   --corpus <jsonl>                    hunt an unknown one
              emit     --corpus <jsonl> --sequence <ops>   print decoded first blocks
              constants --corpus <jsonl> --sequence <ops>  sweep one seed's keystream
              solve    --pairs <seed:mixed,...>         the four constants from two seeds
              lane32   --corpus <jsonl> --sequence <ops>   the 32-bit lane, given the constants
              lane8    --corpus <jsonl> --sequence <ops>   the 8-bit lane, given the constants

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
              --seed N         the seed constants sweeps (default: the one with most payloads)
              --seed-b N       the seed a survivor must also explain (default: the next one)
              --min-payloads N smallest seed constants will consider (default 40)
              --constants A:O:add|sub   the keystream constants the lane searches use
              --check FILE     a second corpus a recovered 8-bit lane is scored against

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

/// <summary>
/// Recover one seed's keystream, and with it the build's four constants.
///
/// The 64-bit lane is keyed by the seed for the first block only; every block
/// after it is keyed by a state derived from `prng_a`, which is `mixed *
/// MULTIPLIER` for a 32-bit `mixed` that the four constants produce. So this
/// sweeps `mixed` over 2^32 for one seed and keeps the values under which that
/// seed's payloads still read as rep layout past their first block.
///
/// It is a search over a keystream rather than over four constants, and it is
/// what the algebra in docs/payload-transform-13-04.md needs before it can run:
/// `state2` cannot be observed directly, and a `mixed` for two seeds pins
/// `seed_addend`, `init_a_offset` and its sign between them.
/// </summary>
void Constants()
{
    var path = Require("corpus");
    var threads = OptionInt("threads", Environment.ProcessorCount);
    var stageN = OptionInt("stage-n", SeedCorpus.StagedPayloads);
    var limit = OptionInt("rank-n", 200);
    var expect = options.TryGetValue("expect", out var build) ? build : null;

    var sequence = options.TryGetValue("sequence", out var spec)
        ? spec
        : expect is not null && known.TryGetValue(expect, out var published)
            ? published
            : throw new ArgumentException("--sequence or a known --expect is required");
    var lane = new Lane(Parse(sequence));

    var ranked = SeedCorpus.RankSeeds(path, lane, MixedSweep.MinExact);
    if (ranked.Length < 2)
    {
        throw new InvalidOperationException(
            "two seeds are needed, each with payloads of a whole number of 64-bit blocks");
    }

    Console.WriteLine("seed      whole payloads    keystream states they exercise");
    foreach (var row in ranked.Take(6))
    {
        Console.WriteLine($"{row.Seed,8}  {row.Count,15:N0}  {row.States,29:N0}");
    }

    Console.WriteLine();
    var seedA = options.TryGetValue("seed", out var wantedA) && wantedA.Length > 0
        ? uint.Parse(wantedA, CultureInfo.InvariantCulture)
        : ranked[0].Seed;
    var seedB = options.TryGetValue("seed-b", out var wantedB) && wantedB.Length > 0
        ? uint.Parse(wantedB, CultureInfo.InvariantCulture)
        : ranked.First(r => r.Seed != seedA).Seed;

    var corpusA = SeedCorpus.Load(path, seedA, limit);
    var stage = Math.Min(stageN, corpusA.Payloads.Length);

    // Several check seeds rather than one, because a seed that opens cleanly
    // can still fail to decode whole under the right keystream -- on 12.10 the
    // second-ranked seed does exactly that, and checking against it alone
    // rejects the published constants while keeping 160 wrong ones. What a
    // candidate is ranked by is how many check seeds it explains, and the
    // answer explains all the ones that are chains.
    var checkSeeds = ranked
        .Select(r => r.Seed)
        .Where(seed => seed != seedA)
        .Take(OptionInt("check-seeds", 4))
        .ToArray();
    var checks = checkSeeds.Select(seed => SeedCorpus.Load(path, seed, limit)).ToArray();

    Console.WriteLine($"lane    {sequence}");
    Console.WriteLine($"sweep   seed {seedA} -- {corpusA.Payloads.Length:N0} whole payloads, {stage} swept "
        + $"({string.Join(", ", corpusA.Payloads.Take(stage).Select(p => p.Bits))} bits)");
    Console.WriteLine($"check   seeds {string.Join(", ", checkSeeds)}");

    BuildConstants? truth = null;
    if (expect is not null && Published.TryGetValue(expect, out var published2))
    {
        truth = published2;
        Console.WriteLine($"expect  {expect} -- {truth}");
    }

    var clock = Stopwatch.StartNew();
    var survivors = MixedSweep.Run(corpusA, lane, stage, threads);
    clock.Stop();
    Console.WriteLine($"swept   2^32 in {clock.Elapsed.TotalSeconds:N1}s -- {survivors.Count:N0} keystreams kept");

    // One seed cannot name the constants: a keystream that decodes its payloads
    // is consistent with 128 offsets per sign, and the sweep keeps every
    // keystream that seed cannot tell apart. The check seeds settle both at
    // once, because the constants a survivor implies predict *their* keystreams
    // too -- and predicting a seed the sweep never saw is a far stronger claim
    // than agreeing with the one it was fitted to.
    var confirmed = new List<(BuildConstants Constants, uint MixedA, int Explains)>();
    Parallel.ForEach(
        survivors,
        new ParallelOptions { MaxDegreeOfParallelism = threads },
        () => new List<(BuildConstants, uint, int)>(),
        (survivor, loop, local) =>
        {
            var buffer = new byte[SeedCorpus.MaxBits / 8];
            foreach (var candidate in Solve.Candidates(seedA, survivor.Mixed))
            {
                var explains = 0;
                foreach (var check in checks)
                {
                    var mixed = Keystream.Mixed(
                        check.Seed, candidate.SeedAddend, candidate.InitAOffset, candidate.InitAAdds);
                    var states = new uint[check.Payloads.Max(p => p.Blocks)];
                    if (MixedSweep.Exact(mixed, check.Seed, lane, check.Payloads, states, buffer)
                        >= MixedSweep.MinExact)
                    {
                        explains++;
                    }
                }

                if (explains > 0)
                {
                    local.Add((candidate, survivor.Mixed, explains));
                }
            }

            return local;
        },
        local =>
        {
            lock (confirmed)
            {
                confirmed.AddRange(local);
            }
        });

    var best = confirmed.Count == 0 ? 0 : confirmed.Max(c => c.Explains);
    Console.WriteLine($"checked {confirmed.Count:N0} explain at least one check seed; "
        + $"the best explain {best} of {checks.Length}\n");

    foreach (var (constants, mixedA, explains) in confirmed
        .Where(c => c.Explains == best)
        .DistinctBy(c => c.Constants)
        .Take(OptionInt("top", 10)))
    {
        var mark = truth is not null && constants == truth ? "  <- expected" : "";
        Console.WriteLine($"{constants}{mark}");
        Console.WriteLine($"    explains {explains} of {checks.Length} check seeds; "
            + $"mixed at seed {seedA} = 0x{mixedA:X8}");
    }

    if (truth is not null)
    {
        var hit = confirmed.FirstOrDefault(c => c.Constants == truth);
        Console.WriteLine(hit.Constants is null
            ? "\nNOT RECOVERED -- the published constants did not survive"
            : $"\nrecovered, explaining {hit.Explains} of {checks.Length} check seeds");
    }
}


/// <summary>
/// The four constants, from the `mixed` two seeds resolved to.
///
/// One seed leaves 128 candidates per sign, because the only part of
/// `seed -+ init_a_offset` that survives the shift left by 25 is its low seven
/// bits. A second seed picks out the pair that explains both, and a third would
/// only repeat the check.
/// </summary>
void SolveConstants()
{
    var observations = new List<(uint Seed, uint Mixed)>();
    foreach (var pair in Require("pairs").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
    {
        var halves = pair.Split(':');
        if (halves.Length != 2)
        {
            throw new ArgumentException($"expected seed:mixed, got '{pair}'");
        }

        var mixedText = halves[1].StartsWith("0x", StringComparison.OrdinalIgnoreCase) ? halves[1][2..] : halves[1];
        observations.Add((
            uint.Parse(halves[0], CultureInfo.InvariantCulture),
            uint.Parse(mixedText, NumberStyles.HexNumber, CultureInfo.InvariantCulture)));
    }

    foreach (var (seed, mixed) in observations)
    {
        Console.WriteLine($"seed {seed,8} -- mixed 0x{mixed:X8}");
    }

    var solutions = Solve.FromMixed(observations);
    Console.WriteLine();
    if (solutions.Count == 0)
    {
        Console.WriteLine("no constants explain both seeds -- one of the keystreams is wrong");
        return;
    }

    foreach (var solution in solutions)
    {
        Console.WriteLine(solution.ToString());
    }

    if (solutions.Count > 1)
    {
        Console.WriteLine("\nmore than one solution: a third seed decides between them");
    }
}


/// <summary>
/// The keystream constants a lane search runs under: either a published build's
/// or a recovered pair, written seed_addend:offset:add|sub.
/// </summary>
BuildConstants ConstantsFrom(string? expect)
{
    if (options.TryGetValue("constants", out var spec) && spec.Length > 0)
    {
        var parts = spec.Split(':');
        if (parts.Length != 3)
        {
            throw new ArgumentException($"expected seed_addend:offset:add|sub, got '{spec}'");
        }

        var addend = uint.Parse(parts[0], NumberStyles.HexNumber, CultureInfo.InvariantCulture);
        var offset = uint.Parse(parts[1], NumberStyles.HexNumber, CultureInfo.InvariantCulture);
        var adds = parts[2].Equals("add", StringComparison.OrdinalIgnoreCase);
        return new BuildConstants(addend, offset, adds, (byte)(addend & 0xFF));
    }

    if (expect is not null && Published.TryGetValue(expect, out var published))
    {
        return published;
    }

    throw new ArgumentException("--constants or a known --expect is required");
}

/// <summary>
/// The 32-bit lane, scored over the payloads that reach it exactly once.
///
/// Every candidate is a complement variant of the recovered 64-bit skeleton, and
/// the score is how many payloads decode to a rep layout that consumes every
/// bit. The published lanes score 15 to 22 payloads where every other variant
/// scores zero, so this reads as an answer rather than as a ranking.
/// </summary>
void Lane32Command()
{
    var path = Require("corpus");
    var expect = options.TryGetValue("expect", out var build) ? build : null;
    var constants = ConstantsFrom(expect);
    var sequence = options.TryGetValue("sequence", out var spec)
        ? spec
        : expect is not null && known.TryGetValue(expect, out var published)
            ? published
            : throw new ArgumentException("--sequence or a known --expect is required");

    var lane = new Lane(Parse(sequence));
    var payloads = Tail32.Load(path, OptionInt("rank-n", 800));
    Console.WriteLine($"lane    {sequence}");
    Console.WriteLine($"const   {constants}");
    Console.WriteLine($"corpus  {payloads.Count:N0} payloads of a whole number of blocks plus 32 bits\n");

    var rows = Lane32Search.Variants(Parse(sequence))
        .Select(variant => (Variant: variant, Score: Lane32Search.Score(variant, lane, constants, payloads)))
        .OrderByDescending(r => r.Score)
        .ToList();

    foreach (var (variant, score) in rows.Take(OptionInt("top", 8)))
    {
        Console.WriteLine($"{score,5:N0} of {payloads.Count:N0}  {Lane32Search.Describe(variant)}");
    }
}

/// <summary>
/// The 8-bit lane, from payloads whose last byte the rep layout pins.
///
/// Unlike the other two lanes this one is a search rather than a neighbourhood,
/// because its operands are arbitrary multipliers. What makes it tractable is in
/// Lane8Search: a byte operand only depends on its multiplier modulo 256, a run
/// of adds is one slot, and the final slot is solved rather than enumerated.
/// </summary>
void Lane8Command()
{
    var path = Require("corpus");
    var threads = OptionInt("threads", Environment.ProcessorCount);
    var expect = options.TryGetValue("expect", out var build) ? build : null;
    var constants = ConstantsFrom(expect);
    var sequence = options.TryGetValue("sequence", out var spec)
        ? spec
        : expect is not null && known.TryGetValue(expect, out var published)
            ? published
            : throw new ArgumentException("--sequence or a known --expect is required");

    var candidate = Parse(sequence);
    var lane = new Lane(candidate);
    // Two quotas, because the two kinds of case do different jobs. A fitted
    // case has its final byte slot solved from its plaintext, so it must be
    // fully pinned; a masked one pins seven bits of eight and is what the
    // held-out filter and the multiplier recovery run on, because those are the
    // only cases whose plaintext is ever anything but zero.
    var cases = Lane8Search.Cases(path, lane, constants, OptionInt("pinned", 24), OptionInt("rank-n", 1000));
    var pinned = cases.Count(probe => probe.Mask == 0xFF);

    // A fitted case has to be fully pinned, because the final byte slot is
    // solved from its plaintext -- and it has to have an **odd** state, because
    // solving that slot inverts a multiplication by it. An odd state names one
    // multiplier per operand; an even one names up to 128, and every one of them
    // is a separate candidate to test. Six even-state fitted cases turned a
    // three-minute search into one that had not finished in twenty-two.
    var fit = cases.Where(probe => probe.Mask == 0xFF && (probe.State & 1) == 1).Take(6).ToList();
    if (fit.Count < 6)
    {
        Console.WriteLine($"only {fit.Count} payloads pin their last byte whole under an odd state "
            + $"({pinned} pin it at all); a longer corpus is needed");
        return;
    }

    // The held-out filter runs inside the search, once per surviving candidate,
    // so it is a subset; the multiplier recovery runs a few dozen times in all
    // and gets every case there is, because what it needs is distinct states.
    var held = cases.Where(probe => !fit.Contains(probe)).Take(OptionInt("held", 60)).ToList();
    var shapes = Lane8Search.Shapes(candidate);
    var searchable = shapes.Count(Lane8Search.Searchable);

    Console.WriteLine($"lane    {sequence}");
    Console.WriteLine($"const   {constants}");
    Console.WriteLine($"cases   {cases.Count:N0} payloads pin their last byte -- {pinned} of them whole and "
        + $"{cases.Count - pinned} to {Lane8Search.MinPinnedBits} bits of 8; {fit.Count} fitted, "
        + $"{held.Count} held out, all {cases.Count:N0} used to recover the multipliers");
    Console.WriteLine($"shapes  {searchable} of {shapes.Count}, byte slots searched over 256 residues, "
        + $"rotate distances over all {Lane8Search.DistanceCount} values per case");
    if (searchable < shapes.Count)
    {
        Console.WriteLine($"        {shapes.Count - searchable} skipped for carrying more than "
            + $"{Lane8Search.MaxByteSlots} byte slots");
    }

    Console.WriteLine();

    var clock = Stopwatch.StartNew();
    var fits = Lane8Search.Run(shapes, fit, held, threads, OptionInt("shortlist", 20_000));
    clock.Stop();

    if (fits.Count == 0)
    {
        Console.WriteLine($"nothing explains the fitted cases ({clock.Elapsed.TotalSeconds:N1}s)");
        return;
    }

    Console.WriteLine($"fitted  {fits.Count:N0} sets of byte multipliers explain the {fit.Count} fitted cases "
        + $"({clock.Elapsed.TotalSeconds:N1}s)\n");

    // A lane that holds every case is not yet an answer: the fitting stage let
    // each case choose its own rotate distances, so what remains is whether one
    // multiplier per slot produces the distances they all needed. A lane whose
    // distances no multiplier explains is discarded here rather than reported.
    var top = OptionInt("top", 8);
    var holders = fits.Where(f => f.Held == held.Count).ToList();
    if (holders.Count == 0)
    {
        Console.WriteLine("nothing holds every held-out case, so nothing here is the lane. The best few:\n");
        foreach (var found in fits.OrderByDescending(f => f.Held).Take(top))
        {
            Console.WriteLine($"holds {found.Held,3:N0} of {held.Count:N0}  "
                + $"{Lane8Search.Describe(found.Shape, found.Bytes, null)}");
        }

        Console.WriteLine($"\n{clock.Elapsed.TotalSeconds:N1}s");
        return;
    }

    // A second corpus the search never saw. Its cases are scored against the
    // recovered lane in its exact form -- multipliers and all -- which is a
    // stricter question than the one the search answered, and the only one that
    // is not fitted to the corpus it came from.
    var check = options.TryGetValue("check", out var checkPath) && checkPath.Length > 0
        ? Lane8Search.Cases(checkPath, lane, constants, OptionInt("pinned", 24), OptionInt("rank-n", 1000))
        : null;

    var recovering = Stopwatch.StartNew();
    var attempts = OptionInt("recover", 64);
    int explained = 0, unexplained = 0, loose = 0;
    foreach (var found in holders.Take(attempts))
    {
        var recovery = Lane8Search.Recover(found.Shape, found.Bytes, cases, threads, 4);
        if (recovery.Underconstrained)
        {
            loose++;
            continue;
        }

        if (recovery.Multipliers.Count == 0)
        {
            unexplained++;
            continue;
        }

        explained++;
        if (explained > top)
        {
            continue;
        }

        foreach (var rotate in recovery.Multipliers)
        {
            var here = Lane8Search.Holds(found.Shape, found.Bytes, rotate, cases);
            var elsewhere = check is null
                ? string.Empty
                : $", {Lane8Search.Holds(found.Shape, found.Bytes, rotate, check):N0} of {check.Count:N0} on the check corpus";
            Console.WriteLine($"holds {here:N0} of {cases.Count:N0}{elsewhere}");
            Console.WriteLine($"      {Lane8Search.Describe(found.Shape, found.Bytes, rotate)}");
        }
    }

    recovering.Stop();
    Console.WriteLine(
        $"\nheld    {holders.Count:N0} of them hold every held-out case; {explained:N0} have a multiplier "
        + $"per rotate slot, {unexplained:N0} have none and {loose:N0} left a slot unconstrained");
    if (holders.Count > attempts)
    {
        Console.WriteLine($"        {holders.Count - attempts:N0} were not attempted (--recover to raise)");
    }

    Console.WriteLine($"\n{clock.Elapsed.TotalSeconds:N1}s searching, "
        + $"{recovering.Elapsed.TotalSeconds:N1}s recovering multipliers");
}
