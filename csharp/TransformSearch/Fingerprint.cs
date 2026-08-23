using System.Numerics;

namespace TransformSearch;

/// <summary>
/// What a correctly decoded first block looks like, as a bit mask and a score.
///
/// A transform carries no checksum and no redundancy, so a wrong output is the
/// right length and looks random. What separates right from wrong is that the
/// plaintext underneath is stock UE: one bit, then <c>SerializeIntPacked</c>
/// (handle, num_bits) pairs, where each packed byte's low bit is a
/// continuation flag that is almost always clear and each handle is a small
/// ascending integer. That leaves fixed bit positions heavily biased toward
/// zero, and the bias is a property of the framing rather than of any build.
///
/// **Measured, not assumed.** Decoding three corpora with their own published
/// transforms -- 12.10, 12.11 and 13.00, three patches on three maps, about
/// 40,000 distinct first blocks each -- the 21 bits below come out biased to
/// zero at rates agreeing across all three to within 0.03: bit 7 at
/// 0.956/0.958/0.935, bit 0 at 0.928/0.927/0.914, bit 12 at
/// 0.931/0.918/0.916, and so on down to 0.75. That agreement across builds is
/// the licence to score a build whose answer is unknown against a mask
/// measured on builds whose answers are known.
///
/// The identity -- the raw ciphertext -- biases these same bits the *other*
/// way, to about 0.4, so a near-identity composition scores worse than random
/// rather than sneaking through.
/// </summary>
public static class Fingerprint
{
    /// <summary>
    /// Bits 0,1,5,7,8,9,10,11,12,13,18,19,25,26,33,39,41,43,44,45,48 -- every
    /// bit whose zero-rate under a correct decode is at least 0.75.
    /// </summary>
    public const ulong Mask = 0x00013A82060C3FA3UL;

    /// <summary>
    /// XORed in before counting, so every selected bit is one that should read
    /// zero. It is currently zero because every selected bit is already biased
    /// toward zero; it exists so the mask can grow a bit that is not.
    /// </summary>
    public const ulong Target = 0x0UL;

    public const int SelectedBits = 21;

    /// <summary>Mean set bits per payload for a correct decode: 3.49/3.67/3.69 measured.</summary>
    public const double MeanCorrect = 3.6;

    /// <summary>Mean set bits per payload for a wrong one. Half of 21, and measured at 9.8-12.1.</summary>
    public const double MeanRandom = 10.5;

    public static long Score(ulong[] values, int n)
    {
        long total = 0;
        for (var i = 0; i < n; i++)
        {
            total += BitOperations.PopCount((values[i] ^ Target) & Mask);
        }

        return total;
    }

    /// <summary>
    /// A cut this many standard deviations below the random mean.
    ///
    /// The two populations are about 7 bits per payload apart with a spread of
    /// 2.3, so the midpoint is many sigma from both and the exact cut hardly
    /// matters -- what matters is that it is derived from the calibration
    /// rather than tuned until something interesting appeared.
    /// </summary>
    public static long Threshold(int n)
    {
        var midpoint = (MeanCorrect + MeanRandom) / 2.0;
        return (long)Math.Floor(midpoint * n);
    }
}
