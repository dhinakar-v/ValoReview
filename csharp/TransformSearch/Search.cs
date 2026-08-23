using System.Collections.Concurrent;
using System.Numerics;

namespace TransformSearch;

public sealed record Candidate(int[] Kinds, int[] Ks, long StageScore)
{
    public int Depth => Kinds.Length;

    public string Describe() =>
        string.Join(" -> ", Enumerable.Range(0, Depth).Select(i => Ops.Name(Kinds[i], Ks[i])));
}

public sealed record SearchReport(
    List<Candidate> Survivors,
    long NodesVisited,
    bool Overflowed,
    long OverflowCount);

/// <summary>
/// Depth-first enumeration of compositions, scored at every node.
///
/// Two things make an otherwise hopeless space enumerable.
///
/// **Operands descend.** Across all five published transforms' 64-bit lanes --
/// 35 operand uses -- the rotation amount k of each successive state operand is
/// strictly smaller than the last: 12.10 uses 8,6,5,4; 12.11 uses 8,6,4,3,2;
/// 13.00 uses 8,6,3,1; 13.01 uses 5,4,1; 13.02 uses 6,3,2. Never a repeat,
/// never an ascent. Imposing that turns the operand choice for m operand ops
/// from 8^m into C(8,m) -- for m=5, 56 instead of 32,768 -- and collapses depth
/// seven from about 10^12 compositions to about 5x10^8. It is a *prior* and not
/// a proof, which is why --loose relaxes it to non-strict and why the
/// validation run has to recover a known answer under it first.
///
/// **Prefixes are shared.** The score needs the decoded values, so a
/// depth-first walk keeping one array of partially-decoded payloads per level
/// pays one op per node rather than a whole composition per leaf.
/// </summary>
public sealed class Search
{
    private readonly Corpus corpus;
    private readonly int maxDepth;
    private readonly int minDepth;
    private readonly long threshold;
    private readonly bool strict;
    private readonly int maxK;

    public Search(Corpus corpus, int maxDepth, int minDepth, long threshold, bool strict, int maxK)
    {
        this.corpus = corpus;
        this.maxDepth = maxDepth;
        this.minDepth = minDepth;
        this.threshold = threshold;
        this.strict = strict;
        this.maxK = maxK;
    }

    /// <summary>
    /// Compositions equivalent to a shorter or already-enumerated one.
    ///
    /// Each of these is an identity rather than a heuristic, so pruning them
    /// removes nothing the search could otherwise find. NOT, swap64 and
    /// reverse64 are involutions, so an immediate repeat is the identity; NOT
    /// followed by "xor ror_k" *is* "xor ~ror_k", which the vocabulary already
    /// carries at the same k; and swap64 and reverse64 commute -- both are XORs
    /// of the bit index, by 1 and by 47 -- so only one of the two orders is
    /// needed.
    /// </summary>
    private static bool Allowed(int kind, int lastKind) => (lastKind, kind) switch
    {
        (Ops.Not, Ops.Not) => false,
        (Ops.Swap, Ops.Swap) => false,
        (Ops.Reverse, Ops.Reverse) => false,
        (Ops.Not, Ops.Xor) => false,
        (Ops.Not, Ops.XorNot) => false,
        (Ops.Swap, Ops.Reverse) => false,
        _ => true,
    };

    private static void ApplyOp(int kind, int k, ulong[] src, ulong[] dst, int n, ulong[] ror, int[] amt)
    {
        var off = k - 1;
        switch (kind)
        {
            case Ops.Swap:
                for (var i = 0; i < n; i++)
                {
                    dst[i] = Ops.Swap64(src[i]);
                }

                break;
            case Ops.Reverse:
                for (var i = 0; i < n; i++)
                {
                    dst[i] = Ops.Reverse64(src[i]);
                }

                break;
            case Ops.Sbox:
                for (var i = 0; i < n; i++)
                {
                    dst[i] = Ops.Sbox64(src[i]);
                }

                break;
            case Ops.Not:
                for (var i = 0; i < n; i++)
                {
                    dst[i] = ~src[i];
                }

                break;
            case Ops.Add:
                for (var i = 0; i < n; i++)
                {
                    dst[i] = src[i] + ror[(i * Ops.Stride) + off];
                }

                break;
            case Ops.Sub:
                for (var i = 0; i < n; i++)
                {
                    dst[i] = src[i] - ror[(i * Ops.Stride) + off];
                }

                break;
            case Ops.Xor:
                for (var i = 0; i < n; i++)
                {
                    dst[i] = src[i] ^ ror[(i * Ops.Stride) + off];
                }

                break;
            case Ops.XorNot:
                for (var i = 0; i < n; i++)
                {
                    dst[i] = src[i] ^ ~ror[(i * Ops.Stride) + off];
                }

                break;
            case Ops.RotR:
                for (var i = 0; i < n; i++)
                {
                    dst[i] = BitOperations.RotateRight(src[i], amt[(i * Ops.Stride) + off]);
                }

                break;
            case Ops.RotL:
                for (var i = 0; i < n; i++)
                {
                    dst[i] = BitOperations.RotateLeft(src[i], amt[(i * Ops.Stride) + off]);
                }

                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(kind));
        }
    }

    private sealed class Worker
    {
        public required ulong[][] Levels { get; init; }

        public required int[] Kinds { get; init; }

        public required int[] Ks { get; init; }

        public long Nodes { get; set; }

        /// <summary>
        /// The best <see cref="PerThreadKeep"/> compositions this thread saw,
        /// as a heap keyed on the negated score so that dequeuing evicts the
        /// *worst* one held.
        /// </summary>
        public PriorityQueue<Candidate, long> Best { get; } = new();

        public long Evicted { get; set; }
    }

    /// <summary>
    /// How many compositions one thread keeps.
    ///
    /// This is a bound on memory, not on the answer: the heap always holds the
    /// best ones seen, so a candidate is only ever evicted by a strictly better
    /// candidate. An earlier version kept everything under a threshold up to a
    /// flat cap and then dropped the rest -- which discards by arrival order,
    /// so on a run that overflowed, the reported ranking could not be trusted.
    /// </summary>
    private const int PerThreadKeep = 20_000;

    public SearchReport Run(int degreeOfParallelism)
    {
        var prefixes = EnumeratePrefixes(Math.Min(2, maxDepth));
        var workers = new ConcurrentBag<Worker>();
        var n = corpus.Count;

        var local = new ThreadLocal<Worker>(() =>
        {
            var created = new Worker
            {
                Levels = [.. Enumerable.Range(0, maxDepth + 1).Select(_ => new ulong[n])],
                Kinds = new int[maxDepth],
                Ks = new int[maxDepth],
            };
            workers.Add(created);
            return created;
        });

        Parallel.ForEach(
            prefixes,
            new ParallelOptions { MaxDegreeOfParallelism = degreeOfParallelism },
            prefix =>
            {
                var worker = local.Value!;
                Array.Copy(corpus.Values, worker.Levels[0], n);
                for (var d = 0; d < prefix.Kinds.Length; d++)
                {
                    worker.Kinds[d] = prefix.Kinds[d];
                    worker.Ks[d] = prefix.Ks[d];
                    ApplyOp(
                        prefix.Kinds[d],
                        Math.Max(prefix.Ks[d], 1),
                        worker.Levels[d],
                        worker.Levels[d + 1],
                        n,
                        corpus.Ror,
                        corpus.Amt);
                }

                Descend(worker, prefix.Kinds.Length, prefix.MaxK, prefix.LastKind);
            });

        var all = workers.ToList();
        var survivors = all.SelectMany(w => w.Best.UnorderedItems.Select(e => e.Element))
            .OrderBy(c => c.StageScore)
            .ToList();
        var evicted = all.Sum(w => w.Evicted);
        return new SearchReport(survivors, all.Sum(w => w.Nodes), evicted > 0, evicted);
    }

    private void Descend(Worker worker, int depth, int allowedMaxK, int lastKind)
    {
        worker.Nodes++;
        var n = corpus.Count;

        if (depth >= minDepth)
        {
            var score = Fingerprint.Score(worker.Levels[depth], n);
            if (score <= threshold)
            {
                worker.Best.Enqueue(new Candidate(worker.Kinds[..depth], worker.Ks[..depth], score), -score);
                if (worker.Best.Count > PerThreadKeep)
                {
                    worker.Best.Dequeue();
                    worker.Evicted++;
                }
            }
        }

        if (depth == maxDepth)
        {
            return;
        }

        for (var kind = 0; kind < Ops.KindCount; kind++)
        {
            if (!Allowed(kind, lastKind))
            {
                continue;
            }

            if (kind < Ops.FirstOperandKind)
            {
                worker.Kinds[depth] = kind;
                worker.Ks[depth] = 0;
                ApplyOp(kind, 1, worker.Levels[depth], worker.Levels[depth + 1], n, corpus.Ror, corpus.Amt);
                Descend(worker, depth + 1, allowedMaxK, kind);
                continue;
            }

            for (var k = allowedMaxK; k >= 1; k--)
            {
                worker.Kinds[depth] = kind;
                worker.Ks[depth] = k;
                ApplyOp(kind, k, worker.Levels[depth], worker.Levels[depth + 1], n, corpus.Ror, corpus.Amt);
                Descend(worker, depth + 1, strict ? k - 1 : k, kind);
            }
        }
    }

    private sealed record Prefix(int[] Kinds, int[] Ks, int MaxK, int LastKind);

    /// <summary>
    /// Every valid op sequence of a given short length, as parallel work items.
    ///
    /// Splitting at depth two rather than depth one matters: the subtree under
    /// an operand op with k=8 is far larger than the one under k=1, so 52
    /// top-level branches across twelve threads would leave most of them idle
    /// while one finished.
    /// </summary>
    private List<Prefix> EnumeratePrefixes(int depth)
    {
        var acc = new List<Prefix>();
        Walk([], [], maxK, -1);
        return acc;

        void Walk(int[] kinds, int[] ks, int allowedMaxK, int lastKind)
        {
            if (kinds.Length == depth)
            {
                acc.Add(new Prefix(kinds, ks, allowedMaxK, lastKind));
                return;
            }

            for (var kind = 0; kind < Ops.KindCount; kind++)
            {
                if (!Allowed(kind, lastKind))
                {
                    continue;
                }

                if (kind < Ops.FirstOperandKind)
                {
                    Walk([.. kinds, kind], [.. ks, 0], allowedMaxK, kind);
                    continue;
                }

                for (var k = allowedMaxK; k >= 1; k--)
                {
                    Walk([.. kinds, kind], [.. ks, k], strict ? k - 1 : k, kind);
                }
            }
        }
    }

    /// <summary>The decoded first blocks a composition produces.</summary>
    public static ulong[] Decode(Candidate candidate, Corpus corpus)
    {
        var n = corpus.Count;
        var src = new ulong[n];
        var dst = new ulong[n];
        Array.Copy(corpus.Values, src, n);
        for (var d = 0; d < candidate.Depth; d++)
        {
            ApplyOp(candidate.Kinds[d], Math.Max(candidate.Ks[d], 1), src, dst, n, corpus.Ror, corpus.Amt);
            (src, dst) = (dst, src);
        }

        return src;
    }

    /// <summary>Re-run one composition over a larger corpus, for ranking survivors.</summary>
    public static long Rescore(Candidate candidate, Corpus corpus) =>
        Fingerprint.Score(Decode(candidate, corpus), corpus.Count);
}
