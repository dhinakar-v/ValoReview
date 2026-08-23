using Replay.Models.Descriptors;

namespace Replay.Unreal.Parsing;

internal sealed class DescriptorCatalogIndex
{
    private static readonly StringComparer PathComparer = StringComparer.Ordinal;

    private readonly Dictionary<string, ExportGroupDescriptor> _exportDescriptorsByPath = new(PathComparer);
    private readonly Dictionary<string, ExportGroupKind> _exportKindsByDefaultObjectName = new(PathComparer);
    private readonly Dictionary<string, ClassNetCacheDescriptor> _cacheDescriptorsByPath = new(PathComparer);

    public void SetCatalog(DescriptorCatalog descriptorCatalog)
    {
        Clear();

        foreach (var descriptor in descriptorCatalog.ExportGroupDescriptors)
        {
            IndexExportDescriptor(descriptor);
        }

        foreach (var descriptor in descriptorCatalog.ClassNetCacheDescriptors)
        {
            IndexClassNetCacheDescriptor(descriptor);
            IndexRpcParameterDescriptors(descriptor);
        }
    }

    public void Clear()
    {
        _exportDescriptorsByPath.Clear();
        _exportKindsByDefaultObjectName.Clear();
        _cacheDescriptorsByPath.Clear();
    }

    public bool TryGetExportDescriptor(string path, out ExportGroupDescriptor descriptor) =>
        TryGetByLookup(_exportDescriptorsByPath, path, ReplayPath.LookupKeys, out descriptor!);

    public bool TryGetClassNetCacheDescriptor(string path, out ClassNetCacheDescriptor descriptor) =>
        TryGetByLookup(_cacheDescriptorsByPath, path, ReplayPath.ClassNetCacheLookupKeys, out descriptor!);

    public ExportGroupKind GetExportGroupKind(string path) =>
        TryGetExportDescriptor(path, out var descriptor)
            ? descriptor.Kind
            : _exportKindsByDefaultObjectName.GetValueOrDefault(path, ExportGroupKind.Unknown);

    public void CollectFields(ExportGroupDescriptor descriptor, List<FieldDescriptor> fields)
    {
        if (descriptor.BaseDescriptor is not null)
        {
            CollectFields(descriptor.BaseDescriptor, fields);
        }
        else if (descriptor.BasePath is not null && TryGetExportDescriptor(descriptor.BasePath, out var baseDescriptor))
        {
            CollectFields(baseDescriptor, fields);
        }

        fields.AddRange(descriptor.Fields);
    }

    private void IndexExportDescriptor(ExportGroupDescriptor descriptor)
    {
        foreach (var key in ReplayPath.LookupKeys(descriptor.Path))
        {
            _exportDescriptorsByPath[key] = descriptor;
        }

        if (ReplayPath.GetDefaultObjectName(descriptor.Path) is { } defaultObjectName)
        {
            _exportDescriptorsByPath[defaultObjectName] = descriptor;
            _exportKindsByDefaultObjectName[defaultObjectName] = descriptor.Kind;
        }
    }

    private void IndexClassNetCacheDescriptor(ClassNetCacheDescriptor descriptor)
    {
        foreach (var key in ReplayPath.ClassNetCacheLookupKeys(descriptor.Path))
        {
            _cacheDescriptorsByPath[key] = descriptor;
        }
    }

    private void IndexRpcParameterDescriptors(ClassNetCacheDescriptor descriptor)
    {
        foreach (var rpcDescriptor in descriptor.FunctionFields)
        {
            if (_exportDescriptorsByPath.ContainsKey(rpcDescriptor.FunctionExportPath))
            {
                continue;
            }

            if (rpcDescriptor.ParameterDescriptor is not null)
            {
                IndexExportDescriptor(rpcDescriptor.ParameterDescriptor);
                continue;
            }

            if (rpcDescriptor.Fields.Count == 0)
            {
                continue;
            }

            var descriptorFromRpc = new ExportGroupDescriptor
            (
                rpcDescriptor.FunctionExportPath,
                rpcDescriptor.Categories,
                ExportGroupKind.ClassNetCache,
                FieldStreamGrammar.FunctionParameters,
                fields: rpcDescriptor.Fields);
            IndexExportDescriptor(descriptorFromRpc);
        }
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
