namespace TransformSearch;

/// <summary>One keystream candidate and how many payloads it decoded whole.</summary>
public sealed record Keyed(uint Mixed, int Exact);

/// <summary>
/// The sweep: every <c>mixed</c> in 0..2^32-1, kept when the seed's payloads
/// decode to rep layouts that consume every bit.
///
/// <c>prng_a</c> is <c>mixed * MULTIPLIER</c> for a 32-bit <c>mixed</c>, and
/// <c>prng_b</c> depends on the seed alone, so one 2^32 sweep produces every
/// state that one seed's payloads use. That is the reduction the four constants
/// hide behind: this recovers a keystream, and two solved seeds then pin the
/// constants algebraically.
///
/// Two other oracles were tried first and both are written into
/// docs/payload-transform-13-04.md, because both look reasonable and neither
/// works. A prefix parse cannot contradict enough -- one seed's payloads are
/// one actor replicating one property layout, so they agree with each other
/// rather than constraining each other, and two per cent of the space survives.
/// The bias mask is worse than useless here: it rewards decoded blocks with few
/// set bits, and over 2^32 candidates the winners are keystreams that drive the
/// lane toward zeros, so the published answer ranked below a million of them.
/// </summary>
public static class MixedSweep
{
    /// <summary>
    /// How many survivors a sweep will hold before giving up.
    ///
    /// It throws rather than truncating: a truncated list discards by arrival
    /// order, which can throw the answer away and makes the ranking mean
    /// nothing. A count this large means the staged payloads are not rep
    /// layouts, which is a fact about the seed rather than about the sweep.
    /// </summary>
    public const int MaxSurvivors = 1 << 20;

    /// <summary>How many of a seed's payloads a candidate must decode whole to be kept.</summary>
    public const int MinExact = 2;

    public static List<Keyed> Run(SeedCorpus corpus, Lane lane, int stagePayloads, int degreeOfParallelism)
    {
        var stage = corpus.Payloads.Take(stagePayloads).ToArray();
        if (stage.Length < MinExact)
        {
            throw new InvalidOperationException(
                $"seed {corpus.Seed} holds {stage.Length} payload(s) of a whole number of blocks; "
                + $"{MinExact} are needed to keep a candidate");
        }

        var depth = stage.Max(p => p.Blocks);
        var survivors = new List<Keyed>();
        var chunks = 1 << 12;
        var chunkSize = (1L << 32) / chunks;

        Parallel.For(
            0,
            chunks,
            new ParallelOptions { MaxDegreeOfParallelism = degreeOfParallelism },
            () => new List<Keyed>(),
            (chunk, loop, local) =>
            {
                var start = chunk * chunkSize;
                var end = start + chunkSize;
                var states = new uint[depth];
                var buffer = new byte[SeedCorpus.MaxBits / 8];

                for (var m = start; m < end; m++)
                {
                    var exact = Exact((uint)m, corpus.Seed, lane, stage, states, buffer);
                    if (exact < MinExact)
                    {
                        continue;
                    }

                    local.Add(new Keyed((uint)m, exact));
                    if (local.Count > MaxSurvivors)
                    {
                        throw new InvalidOperationException(
                            $"more than {MaxSurvivors:N0} keystreams decoded {MinExact} payloads whole; "
                            + "this seed's payloads are not rep layouts -- try the next one");
                    }
                }

                return local;
            },
            local =>
            {
                lock (survivors)
                {
                    survivors.AddRange(local);
                }
            });

        survivors.Sort((a, b) => b.Exact.CompareTo(a.Exact));
        return survivors;
    }

    /// <summary>
    /// How many of the payloads one keystream decodes to a whole rep layout.
    ///
    /// The keystream is generated only as deep as the parse reaches, and the
    /// payloads are shortest first, so a candidate that cannot reach
    /// <see cref="MinExact"/> stops as soon as that is arithmetic rather than a
    /// guess -- which for all but six candidates in a hundred thousand is after
    /// a couple of blocks of the first payload.
    /// </summary>
    public static int Exact(uint mixed, uint seed, Lane lane, Multi[] payloads, uint[] states, byte[] buffer)
    {
        var prngA = mixed * Keystream.Multiplier;
        var prngB = Keystream.InitialPrngB(seed);
        states[0] = seed;
        var generated = 1;
        var exact = 0;

        for (var i = 0; i < payloads.Length; i++)
        {
            var payload = payloads[i];
            while (generated < payload.Blocks)
            {
                states[generated] = Keystream.Advance(ref prngA, ref prngB);
                generated++;
            }

            if (ExactChain.Holds(payload, lane, states, buffer))
            {
                exact++;
            }
            else if (exact + (payloads.Length - i - 1) < MinExact)
            {
                return exact;
            }
        }

        return exact;
    }

    /// <summary>Every payload of the seed, for ranking the handful that survive.</summary>
    public static int Rescore(uint mixed, SeedCorpus corpus, Lane lane)
    {
        var depth = corpus.Payloads.Max(p => p.Blocks);
        var states = Keystream.States(corpus.Seed, mixed, depth);
        var buffer = new byte[SeedCorpus.MaxBits / 8];
        return corpus.Payloads.Count(p => ExactChain.Holds(p, lane, states, buffer));
    }
}
