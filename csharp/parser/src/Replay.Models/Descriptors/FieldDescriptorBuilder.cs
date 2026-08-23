using System.Reflection;

namespace Replay.Models.Descriptors;

public sealed class FieldDescriptorBuilder
{
    internal FieldDescriptorBuilder(
        string? exportName,
        string? propertyName,
        PropertyInfo? targetProperty,
        uint? handle,
        ExportCategory categories)
    {
        ExportName = exportName;
        PropertyName = propertyName;
        TargetProperty = targetProperty;
        Handle = handle;
        Categories = categories;
    }

    private string? ExportName { get; }

    private string? PropertyName { get; }

    private PropertyInfo? TargetProperty { get; }

    private uint? Handle { get; }

    private ExportCategory Categories { get; set; }

    private IFieldDecoderDescriptor? Decoder { get; set; }

    public FieldDescriptorBuilder WithCategories(ExportCategory categories)
    {
        Categories = categories;
        return this;
    }

    public FieldDescriptorBuilder Decode(IFieldDecoderDescriptor decoder)
    {
        Decoder = decoder;
        return this;
    }

    internal FieldDescriptor Build() => new()
    {
        ExportName = ExportName,
        PropertyName = PropertyName,
        TargetProperty = TargetProperty,
        Handle = Handle,
        Categories = Categories,
        Decoder = Decoder,
    };
}