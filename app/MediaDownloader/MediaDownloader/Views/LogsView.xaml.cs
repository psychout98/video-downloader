using System.Windows.Controls;
using MediaDownloader.ViewModels;

namespace MediaDownloader.Views;

public partial class LogsView : UserControl
{
    public LogsView()
    {
        InitializeComponent();
        DataContextChanged += (_, e) =>
        {
            if (e.NewValue is LogsViewModel vm)
            {
                vm.LogsUpdated += () =>
                {
                    if (vm.AutoScroll)
                        LogTextBox.ScrollToEnd();
                };
            }
        };
    }
}
