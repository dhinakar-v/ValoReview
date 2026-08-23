namespace Replay.Unreal.Parsing;

internal sealed class BoundExportStore
{
    private static readonly StringComparer PathComparer = StringComparer.Ordinal;

    private readonly Dictionary<string, BoundExportGroup> _boundGroupsByPath = new(PathComparer);
    private readonly Dictionary<string, BoundClassNetCache> _boundCachesByPath = new(PathComparer);
    private readonly Dictionary<string, List<BoundRpcFunction>> _pendingRpcFunctionsByExportPath = new(PathComparer);
    private readonly Dictionary<uint, string> _pathIndexToPath = new();

    public void SetPathIndex(uint pathNameIndex, string path)
    {
        _pathIndexToPath[pathNameIndex] = path;
    }

    public BoundExportGroup? GetBoundGroup(string path) =>
        TryGetByLookup(_boundGroupsByPath, path, ReplayPath.LookupKeys, out var boundGroup) ? boundGroup : null;

    public BoundExportGroup? GetBoundGroupByIndex(uint pathNameIndex)
    {
        if (_pathIndexToPath.TryGetValue(pathNameIndex, out var path))
        {
            return GetBoundGroup(path);
        }

        return null;
    }

    public BoundClassNetCache? GetBoundCache(string path) =>
        TryGetByLookup(_boundCachesByPath, path, ReplayPath.ClassNetCacheLookupKeys, out var boundCache) ? boundCache : null;

    public BoundClassNetCache? GetBoundCacheByIndex(uint pathNameIndex)
    {
        if (_pathIndexToPath.TryGetValue(pathNameIndex, out var path))
        {
            return GetBoundCache(path);
        }

        return null;
    }

    public bool HasBinding(string path) => GetBoundGroup(path) is not null || GetBoundCache(path) is not null;

    public void IndexBoundExportGroup(string path, BoundExportGroup bound)
    {
        foreach (var key in ReplayPath.LookupKeys(path))
        {
            _boundGroupsByPath[key] = bound;
        }
    }

    public void IndexBoundClassNetCache(string path, BoundClassNetCache bound)
    {
        foreach (var key in ReplayPath.ClassNetCacheLookupKeys(path))
        {
            _boundCachesByPath[key] = bound;
        }
    }

    public void AddPendingRpcFunction(string functionExportPath, BoundRpcFunction function)
    {
        if (!_pendingRpcFunctionsByExportPath.TryGetValue(functionExportPath, out var pendingFunctions))
        {
            pendingFunctions = [];
            _pendingRpcFunctionsByExportPath.Add(functionExportPath, pendingFunctions);
        }

        pendingFunctions.Add(function);
    }

    public void ResolvePendingRpcFunctions(string functionExportPath, BoundExportGroup functionGroup)
    {
        if (!_pendingRpcFunctionsByExportPath.Remove(functionExportPath, out var pendingFunctions))
        {
            return;
        }

        foreach (var pendingFunction in pendingFunctions)
        {
            pendingFunction.FunctionGroup = functionGroup;
        }
    }

    public void Clear()
    {
        _boundGroupsByPath.Clear();
        _boundCachesByPath.Clear();
        _pathIndexToPath.Clear();
        _pendingRpcFunctionsByExportPath.Clear();
    }

    private static bool TryGetByLookup<TValue>(
        Dictionary<string, TValue> valuesByPath,
        string path,
        Func<string, IEnumerable<string>> lookupKeys,
        out TValue value)
    {
        foreach (var key in lookupKeys(path))
        {
            if (valuesByPath.TryGetValue(key, out value!))
            {
                return true;
            }
        }

        value = default!;
        return false;
    }
}
