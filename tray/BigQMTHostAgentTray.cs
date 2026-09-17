// Portable, facts-only Host Agent tray.  It has no QMT, Redis, order, Lease,
// confirmation, or execution API.  All runtime values come from the adjacent
// machine.local.json so the same binary can live in one folder per machine.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class BigQMTHostAgentTray
{
    private static NotifyIcon tray;
    private static ToolStripMenuItem statusItem;
    private static ToolStripMenuItem detailItem;
    private static ToolStripMenuItem startupItem;
    private static Icon currentIcon;
    private static Dictionary<string, object> settings = new Dictionary<string, object>();
    private static DateTime nextDelivery = DateTime.MinValue;
    private static string state = "初始化中";
    private static string detail = "读取 machine.local.json";
    private static readonly object deliveryLock = new object();
    private static bool deliveryBusy;

    private static string RootPath() { return AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\'); }
    private static string ConfigPath() { return Path.Combine(RootPath(), "machine.local.json"); }
    private static string Value(string key, string fallback)
    {
        object value;
        return settings.TryGetValue(key, out value) && value != null && value.ToString().Trim().Length > 0 ? value.ToString().Trim() : fallback;
    }
    private static int IntervalSeconds()
    {
        int result;
        return Int32.TryParse(Value("interval_seconds", "300"), out result) ? Math.Max(30, Math.Min(result, 3600)) : 300;
    }
    private static string ResolvePath(string value)
    {
        if (String.IsNullOrWhiteSpace(value)) return "";
        string normalized = value.Replace('/', '\\');
        return Path.IsPathRooted(normalized) ? normalized : Path.GetFullPath(Path.Combine(RootPath(), normalized));
    }

    [STAThread]
    private static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        LoadSettings();
        string hostId = Value("host_id", "unknown-host").Replace('.', '_').Replace(':', '_');
        bool first;
        using (System.Threading.Mutex mutex = new System.Threading.Mutex(true, "Local\\KitlingBigQMTHostAgent-" + hostId, out first))
        {
            if (!first) return;
            BuildTray();
            Audit("tray_started", "facts_only=true; orders_enabled=false");
            Refresh(true);
            Timer timer = new Timer();
            timer.Interval = 30000;
            timer.Tick += delegate { Refresh(false); };
            timer.Start();
            Application.Run();
            tray.Visible = false;
            if (currentIcon != null) currentIcon.Dispose();
        }
    }

    private static void BuildTray()
    {
        ContextMenuStrip menu = new ContextMenuStrip();
        statusItem = new ToolStripMenuItem("Host Agent：初始化中"); statusItem.Enabled = false; menu.Items.Add(statusItem);
        detailItem = new ToolStripMenuItem("详情：读取配置"); detailItem.Enabled = false; menu.Items.Add(detailItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("立即采集并上报事实", null, delegate { Refresh(true); });
        menu.Items.Add("打开运行目录", null, delegate { Process.Start("explorer.exe", "\"" + RootPath() + "\""); });
        menu.Items.Add("打开日志", null, delegate { OpenLog(); });
        startupItem = new ToolStripMenuItem("随 Windows 启动 Host Agent");
        startupItem.CheckOnClick = true;
        startupItem.Checked = StartupEnabled();
        startupItem.CheckedChanged += delegate { SetStartup(startupItem.Checked); };
        menu.Items.Add(startupItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("退出 Host Agent", null, delegate { Application.Exit(); });
        tray = new NotifyIcon();
        tray.ContextMenuStrip = menu;
        tray.DoubleClick += delegate { Refresh(true); };
        tray.Visible = true;
        SetIcon(false);
    }

    private static void LoadSettings()
    {
        try
        {
            string raw = File.ReadAllText(ConfigPath(), Encoding.UTF8);
            object decoded = new JavaScriptSerializer().DeserializeObject(raw);
            Dictionary<string, object> dictionary = decoded as Dictionary<string, object>;
            if (dictionary == null) throw new InvalidDataException("machine.local.json must be an object");
            settings = dictionary;
        }
        catch (Exception error)
        {
            settings = new Dictionary<string, object>();
            state = "配置错误";
            detail = error.GetType().Name;
        }
    }

    private static void Refresh(bool force)
    {
        lock (deliveryLock)
        {
            if (deliveryBusy) return;
            if (!force && DateTime.UtcNow < nextDelivery) { Paint(); return; }
            deliveryBusy = true;
            nextDelivery = DateTime.UtcNow.AddSeconds(IntervalSeconds());
        }
        System.Threading.ThreadPool.QueueUserWorkItem(delegate
        {
            try { CollectAndDeliver(); }
            finally { lock (deliveryLock) { deliveryBusy = false; } Paint(); }
        });
    }

    private static void CollectAndDeliver()
    {
        LoadSettings();
        string hostId = Value("host_id", "");
        string profile = Value("profile", "simulation");
        string auditPath = ResolvePath(Value("audit_path", ""));
        string outboxPath = ResolvePath(Value("outbox_path", Path.Combine("state", "host_agent_outbox.sqlite3")));
        string secretPath = ResolvePath(Value("fact_secret_path", Path.Combine("secrets", "host-fact.json")));
        string endpoint = Value("coordinator_endpoint", "http://192.0.2.121:18666/api/v1/facts/ingest");
        if (String.IsNullOrEmpty(hostId) || !File.Exists(auditPath)) { SetState("等待审计日志", "audit_path 不存在", false); return; }
        if (!File.Exists(secretPath)) { SetState("等待初始化", "Fact Secret 不存在", false); return; }
        bool collected;
        string collect = RunPython(Path.Combine("scripts", "host_agent", "collect_runtime_fact.py"),
            "--profile " + Quote(profile) + " --host-id " + Quote(hostId) + " --audit-path " + Quote(auditPath) + " --outbox-path " + Quote(outboxPath), 15000, out collected);
        if (!collected) { SetState("采集失败", Short(collect), false); Audit("fact_collect_blocked", Short(collect)); return; }
        bool delivered;
        string deliver = RunPython(Path.Combine("scripts", "host_agent", "deliver_fact_outbox.py"),
            "--profile " + Quote(profile) + " --secret-file " + Quote(secretPath) + " --outbox-path " + Quote(outboxPath) + " --endpoint " + Quote(endpoint), 20000, out delivered);
        bool accepted = delivered && (deliver.IndexOf("\"status\": \"ACCEPTED\"") >= 0 || deliver.IndexOf("\"status\": \"EMPTY\"") >= 0 || deliver.IndexOf("\"status\": \"REPLAYED\"") >= 0);
        SetState(accepted ? "正常" : "待重试", Short(deliver), accepted);
        Audit(accepted ? "host_fact_delivery" : "host_fact_delivery_retry_pending", Short(deliver));
    }

    private static string RunPython(string relativeScript, string arguments, int timeout, out bool ok)
    {
        ok = false;
        try
        {
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = "py.exe";
            info.Arguments = "-3.12 " + Quote(Path.Combine(RootPath(), relativeScript)) + " " + arguments;
            info.WorkingDirectory = RootPath(); info.UseShellExecute = false; info.CreateNoWindow = true;
            info.RedirectStandardOutput = true; info.RedirectStandardError = true;
            using (Process process = Process.Start(info))
            {
                string stdout = process.StandardOutput.ReadToEnd(); string stderr = process.StandardError.ReadToEnd();
                if (!process.WaitForExit(timeout)) { try { process.Kill(); } catch { } return stdout + stderr + " timeout"; }
                ok = process.ExitCode == 0; return stdout + stderr;
            }
        }
        catch (Exception error) { return error.GetType().Name + ": " + error.Message; }
    }

    private static string Quote(string value) { return "\"" + (value ?? "").Replace("\"", "") + "\""; }
    private static string Short(string value) { return (value ?? "").Replace("\r", " ").Replace("\n", " ").Trim().Substring(0, Math.Min(180, (value ?? "").Replace("\r", " ").Replace("\n", " ").Trim().Length)); }
    private static void SetState(string newState, string newDetail, bool healthy) { state = newState; detail = newDetail; SetIcon(healthy); }
    private static void Paint()
    {
        if (tray == null) return;
        statusItem.Text = "Host Agent " + Value("host_id", "未知") + "：" + state + "（只读）";
        detailItem.Text = "详情：" + (detail.Length > 120 ? detail.Substring(0, 120) : detail);
        tray.Text = ("BigQMT Host Agent｜" + state).Substring(0, Math.Min(63, ("BigQMT Host Agent｜" + state).Length));
    }
    private static void SetIcon(bool healthy)
    {
        if (tray == null) return;
        Color color = healthy ? Color.FromArgb(50, 169, 232) : Color.FromArgb(145, 25, 35);
        using (Bitmap bitmap = new Bitmap(32, 32))
        using (Graphics g = Graphics.FromImage(bitmap))
        using (Brush brush = new SolidBrush(color))
        using (Font font = new Font("Segoe UI", 15, FontStyle.Bold, GraphicsUnit.Pixel))
        using (StringFormat format = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
        {
            g.Clear(Color.Transparent); g.FillEllipse(brush, new Rectangle(1, 1, 30, 30));
            g.DrawString("H", font, Brushes.White, new RectangleF(0, 0, 32, 32), format);
            if (currentIcon != null) currentIcon.Dispose();
            currentIcon = Icon.FromHandle(bitmap.GetHicon()); tray.Icon = currentIcon;
        }
        Paint();
    }
    private static void OpenLog()
    {
        string path = Path.Combine(RootPath(), "logs", "host_agent_tray.jsonl");
        Directory.CreateDirectory(Path.GetDirectoryName(path)); if (!File.Exists(path)) File.WriteAllText(path, "", new UTF8Encoding(false));
        Process.Start("notepad.exe", Quote(path));
    }
    private static void Audit(string eventName, string text)
    {
        try
        {
            string dir = Path.Combine(RootPath(), "logs"); Directory.CreateDirectory(dir);
            string line = "{\"event_time\":\"" + DateTime.UtcNow.ToString("o") + "\",\"event\":\"" + Escape(eventName) + "\",\"detail\":\"" + Escape(text) + "\",\"orders_enabled\":false}";
            File.AppendAllText(Path.Combine(dir, "host_agent_tray.jsonl"), line + Environment.NewLine, new UTF8Encoding(false));
        }
        catch { }
    }
    private static string Escape(string value) { return (value ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "\\r").Replace("\n", "\\n"); }
    private static string RunValueName() { return "KitlingBigQMTHostAgent-" + Value("host_id", "unknown").Replace('.', '_'); }
    private static bool StartupEnabled() { using (RegistryKey key = Registry.CurrentUser.OpenSubKey("Software\\Microsoft\\Windows\\CurrentVersion\\Run", false)) return key != null && key.GetValue(RunValueName()) != null; }
    private static void SetStartup(bool enabled)
    {
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey("Software\\Microsoft\\Windows\\CurrentVersion\\Run"))
        {
            if (enabled) key.SetValue(RunValueName(), "\"" + Application.ExecutablePath + "\""); else key.DeleteValue(RunValueName(), false);
        }
        Audit("windows_startup", enabled ? "enabled" : "disabled");
    }
}
