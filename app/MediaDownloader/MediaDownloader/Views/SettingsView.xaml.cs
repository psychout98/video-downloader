using System.Windows;
using System.Windows.Controls;
using MediaDownloader.ViewModels;
using Microsoft.Win32;

namespace MediaDownloader.Views;

public partial class SettingsView : UserControl
{
    public SettingsView()
    {
        InitializeComponent();
        DataContextChanged += OnDataContextChanged;
    }

    private void OnDataContextChanged(object sender, DependencyPropertyChangedEventArgs e)
    {
        if (e.NewValue is SettingsViewModel vm)
        {
            // PasswordBox can't be bound directly — sync manually
            TmdbKeyBox.Password = vm.TmdbApiKey;
            RdKeyBox.Password = vm.RealDebridApiKey;

            vm.PropertyChanged += (_, args) =>
            {
                if (args.PropertyName == nameof(vm.TmdbApiKey) && TmdbKeyBox.Password != vm.TmdbApiKey)
                    TmdbKeyBox.Password = vm.TmdbApiKey;
                if (args.PropertyName == nameof(vm.RealDebridApiKey) && RdKeyBox.Password != vm.RealDebridApiKey)
                    RdKeyBox.Password = vm.RealDebridApiKey;
            };
        }
    }

    private void TmdbKey_Changed(object sender, RoutedEventArgs e)
    {
        if (DataContext is SettingsViewModel vm)
            vm.TmdbApiKey = TmdbKeyBox.Password;
    }

    private void RdKey_Changed(object sender, RoutedEventArgs e)
    {
        if (DataContext is SettingsViewModel vm)
            vm.RealDebridApiKey = RdKeyBox.Password;
    }

    // Folder browse helpers
    private void BrowseFolder(Action<string> setter)
    {
        var dialog = new OpenFolderDialog { Title = "Select Folder" };
        if (dialog.ShowDialog() == true)
            setter(dialog.FolderName);
    }

    private void BrowseFile(Action<string> setter, string filter)
    {
        var dialog = new OpenFileDialog { Filter = filter };
        if (dialog.ShowDialog() == true)
            setter(dialog.FileName);
    }

    private SettingsViewModel? VM => DataContext as SettingsViewModel;

    private void BrowseMediaDir_Click(object s, RoutedEventArgs e) => BrowseFolder(p => VM!.MediaDir = p);
    private void BrowseArchiveDir_Click(object s, RoutedEventArgs e) => BrowseFolder(p => VM!.ArchiveDir = p);
    private void BrowseDownloadsDir_Click(object s, RoutedEventArgs e) => BrowseFolder(p => VM!.DownloadsDir = p);
    private void BrowsePostersDir_Click(object s, RoutedEventArgs e) => BrowseFolder(p => VM!.PostersDir = p);
    private void BrowseMpcBeExe_Click(object s, RoutedEventArgs e)
        => BrowseFile(p => VM!.MpcBeExe = p, "Executable files (*.exe)|*.exe|All files (*.*)|*.*");
}
