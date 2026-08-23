namespace TransformSearch;

/// <summary>
/// A structural check on a decoded first block, independent of the bit mask.
///
/// The mask in <see cref="Fingerprint"/> is a statistical filter: it asks
/// whether the right bits lean the right way. This asks a different question --
/// whether the 64 bits actually *parse* as the opening of a UE
/// backwards-compatible rep layout: one bit, then a
/// <c>SerializeIntPacked</c> handle, then a packed field length, then that many
/// bits, then a strictly larger handle.
///
/// Keeping the two separate is the point. A composition that games a bias mask
/// by some accident of arithmetic still has to produce bits that parse, and
/// vice versa, so agreement between them is real evidence rather than the same
/// evidence counted twice.
/// </summary>
public static class Framing
{
    /// <summary>
    /// A field longer than this inside the first block is taken as a parse
    /// failure. Rep-layout properties that open a payload are small -- a
    /// handful of bits to a few dozen -- and the block only holds 64 anyway.
    /// </summary>
    private const int MaxFieldBits = 64;

    /// <summary>
    /// How many (handle, length) pairs of the chain the first 64 bits parse
    /// into, or -1 if the opening is not a chain at all.
    ///
    /// Running out of bits part way through a pair is a stop, not a failure:
    /// the block is a 64-bit window onto a longer payload, so a truncated pair
    /// is the expected way for it to end.
    /// </summary>
    public static int PairsParsed(ulong block)
    {
        var pos = 1;
        var pairs = 0;
        var previousHandle = 0u;

        while (true)
        {
            if (!TryReadPacked(block, ref pos, out var handle))
            {
                return pairs;
            }

            // A zero handle terminates the chain, which is a clean end.
            if (handle == 0)
            {
                return pairs;
            }

            if (handle <= previousHandle)
            {
                return pairs == 0 ? -1 : pairs;
            }

            if (!TryReadPacked(block, ref pos, out var fieldBits))
            {
                return pairs;
            }

            if (fieldBits == 0 || fieldBits > MaxFieldBits)
            {
                return pairs == 0 ? -1 : pairs;
            }

            pairs++;
            previousHandle = handle;
            pos += (int)fieldBits;
            if (pos >= 64)
            {
                return pairs;
            }
        }
    }

    /// <summary>
    /// The opening parses as at least one complete (handle, length) pair.
    ///
    /// One pair is the useful bar: it consumes 17 bits of a 64-bit window, so
    /// requiring two would mostly measure how short the first property is.
    /// </summary>
    public static bool OpensAsChain(ulong block) => PairsParsed(block) >= 1;

    /// <summary>
    /// UE writes a packed integer as 8-bit groups whose low bit says another
    /// group follows and whose upper seven carry the next seven bits of the
    /// value, least significant group first.
    /// </summary>
    private static bool TryReadPacked(ulong block, ref int pos, out uint value)
    {
        value = 0;
        var shift = 0;
        while (true)
        {
            if (pos + 8 > 64 || shift >= 32)
            {
                return false;
            }

            var group = (uint)((block >> pos) & 0xFF);
            pos += 8;
            value |= (group >> 1) << shift;
            shift += 7;
            if ((group & 1) == 0)
            {
                return true;
            }
        }
    }
}
