using System.Globalization;
using System.Windows;
using MediaDownloader.Converters;

namespace MediaDownloader.Tests;

public class BoolToVisibilityConverterTests
{
    private readonly BoolToVisibilityConverter _converter = new();

    [Fact]
    public void Convert_True_ReturnsVisible()
    {
        var result = _converter.Convert(true, typeof(Visibility), null!, CultureInfo.InvariantCulture);
        Assert.Equal(Visibility.Visible, result);
    }

    [Fact]
    public void Convert_False_ReturnsCollapsed()
    {
        var result = _converter.Convert(false, typeof(Visibility), null!, CultureInfo.InvariantCulture);
        Assert.Equal(Visibility.Collapsed, result);
    }

    [Fact]
    public void Convert_NonBool_ReturnsCollapsed()
    {
        var result = _converter.Convert("not a bool", typeof(Visibility), null!, CultureInfo.InvariantCulture);
        Assert.Equal(Visibility.Collapsed, result);
    }

    [Fact]
    public void Convert_Null_ReturnsCollapsed()
    {
        var result = _converter.Convert(null!, typeof(Visibility), null!, CultureInfo.InvariantCulture);
        Assert.Equal(Visibility.Collapsed, result);
    }

    [Fact]
    public void ConvertBack_Visible_ReturnsTrue()
    {
        var result = _converter.ConvertBack(Visibility.Visible, typeof(bool), null!, CultureInfo.InvariantCulture);
        Assert.Equal(true, result);
    }

    [Fact]
    public void ConvertBack_Collapsed_ReturnsFalse()
    {
        var result = _converter.ConvertBack(Visibility.Collapsed, typeof(bool), null!, CultureInfo.InvariantCulture);
        Assert.Equal(false, result);
    }

    [Fact]
    public void ConvertBack_Hidden_ReturnsFalse()
    {
        var result = _converter.ConvertBack(Visibility.Hidden, typeof(bool), null!, CultureInfo.InvariantCulture);
        Assert.Equal(false, result);
    }
}
