using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

[assembly: AssemblyTitle("ProteomicsQC")]
[assembly: AssemblyProduct("ProteomicsQC")]
[assembly: AssemblyVersion("0.4.0.0")]
[assembly: AssemblyFileVersion("0.4.0.0")]
[assembly: AssemblyInformationalVersion("0.4.0")]

class Launcher {
    static string Quote(string text) {
        var output = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in text) {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { output.Append('\\', slashes * 2 + 1); output.Append(c); }
            else { output.Append('\\', slashes); output.Append(c); }
            slashes = 0;
        }
        output.Append('\\', slashes * 2);
        output.Append('"');
        return output.ToString();
    }

    [STAThread]
    static int Main(string[] args) {
        bool commandLine = args.Length > 0 && args[0] == "--cli";
        bool selfTest = args.Length > 0 && args[0] == "--self-test";
        try {
            string root = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            string python = Path.Combine(root, "_internal", "python", commandLine || selfTest ? "python.exe" : "pythonw.exe");
            string script = Path.Combine(root, "_internal", "app", commandLine ? "msqc2.py" : "msqc_gui.py");
            if (!File.Exists(python) || !File.Exists(script))
                throw new FileNotFoundException("Keep ProteomicsQC.exe together with its _internal folder. Extract the entire ZIP before opening it.");
            var arguments = new StringBuilder("-E -s -B ");
            arguments.Append(Quote(script));
            for (int index = commandLine ? 1 : 0; index < args.Length; index++) {
                arguments.Append(' '); arguments.Append(Quote(args[index]));
            }
            var start = new ProcessStartInfo(python, arguments.ToString());
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.RedirectStandardOutput = true;
            start.RedirectStandardError = true;
            start.WorkingDirectory = Path.Combine(root, "_internal", "app");
            start.EnvironmentVariables.Remove("PYTHONHOME");
            start.EnvironmentVariables.Remove("PYTHONPATH");
            start.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            start.EnvironmentVariables["TCL_LIBRARY"] = Path.Combine(root, "_internal", "python", "tcl", "tcl8.6");
            start.EnvironmentVariables["TK_LIBRARY"] = Path.Combine(root, "_internal", "python", "tcl", "tk8.6");
            using (var process = Process.Start(start)) {
                Task<string> stdout = process.StandardOutput.ReadToEndAsync();
                Task<string> stderr = process.StandardError.ReadToEndAsync();
                process.WaitForExit();
                string output = stdout.Result + stderr.Result;
                if (commandLine) Console.Write(output);
                if (process.ExitCode != 0 && process.ExitCode != 130) {
                    string logRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ProteomicsQC");
                    Directory.CreateDirectory(logRoot);
                    string log = Path.Combine(logRoot, "launcher.log");
                    File.WriteAllText(log, output, Encoding.UTF8);
                    if (!commandLine && !selfTest)
                        MessageBox.Show("The application could not start. Details: " + log, "ProteomicsQC", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
                return process.ExitCode;
            }
        } catch (Exception error) {
            if (!commandLine && !selfTest) MessageBox.Show(error.Message, "ProteomicsQC", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 2;
        }
    }
}
