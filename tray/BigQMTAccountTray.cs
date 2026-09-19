// Native .NET Framework tray. Compile twice with /define:SIMULATION and /define:PRODUCTION.
// It is deliberately read-only: there is no broker, order, or cancel API here.
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Windows.Forms;
using Microsoft.Win32;
using System.Web.Script.Serialization;

internal static class BigQMTAccountTray
{
#if SIMULATION
    private const string Profile = "simulation";
    private const string DefaultAccount = "90000001";
    private const int RedisPort = 6379;
    private const int DashboardPort = 17890;
    private const string DashboardRoute = "/simulation/overview";
    private const string ProfileTitle = "BigQMT 模拟盘";
#else
    private const string Profile = "production_readonly";
    private const string DefaultAccount = "90000002";
    private const int RedisPort = 6380;
    private const int DashboardPort = 17891;
    private const string DashboardRoute = "/production-readonly/overview";
    private const string ProfileTitle = "BigQMT 正式只读";
#endif
    private const string StrategyIdV1115 = "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15";
    private static string Account;

    private static NotifyIcon tray;
    private static ToolStripMenuItem statusItem;
    private static ToolStripMenuItem qmtItem;
    private static ToolStripMenuItem miniQmtItem;
    private static ToolStripMenuItem redisItem;
    private static ToolStripMenuItem bridgeItem;
    private static ToolStripMenuItem dashboardItem;
    private static ToolStripMenuItem coordinatorItem;
    private static ToolStripMenuItem intentItem;
    private static ToolStripMenuItem hostAgentItem;
    private static ToolStripMenuItem strategyDeploymentItem;
    private static ToolStripMenuItem windowsStartupItem;
    private static ToolStripMenuItem strategyPolicyItem;
    private static ToolStripMenuItem strategyPolicyMenu;
    private static MutexHandle mutex;
    private static Icon trayIcon;
    private static string bridgeState = "未探测（只读）";
    private static bool bridgeLiveHealthy = false;
    private static DateTime nextAutoQmtAttempt = DateTime.MinValue;
    private static DateTime nextAutoMiniQmtAttempt = DateTime.MinValue;
    private static DateTime nextBridgeProbeAttempt = DateTime.MinValue;
    private static DateTime nextAutoRedisAttempt = DateTime.MinValue;
    private static DateTime nextAutoDashboardAttempt = DateTime.MinValue;
    private static string lastCoordinatorHeartbeatState = "";
    private static string lastCoordinatorIntentState = "";
    private static string hostAgentState = "未初始化";
    private static string hostAgentDetail = "等待首次心跳";
    private static string configuredHostId = "";
    private static string configuredCoordinatorEndpoint = "";
    private static string configuredFactSecretPath = "";

    // v1.1.15 unattended simulation schedule (simulation profile only).
    // This tray never submits an order itself. It only invokes the fail-closed
    // Python cycle scripts that arm, submit at most one deterministically
    // identified order, then immediately re-lock the runtime control.
    private static readonly object scheduleLock = new object();
    private static bool schedulerBusy = false;
    private static string lastCloseShadowDate = "";
    private static string lastLakeCycleDate = "";
    private static string lastDailyRecordDate = "";
    private static string lastExecutionCycleDate = "";
    // A v1.1.15 rotation is always split into a sell leg and a later buy leg,
    // so "one invocation per session" would strand the sleeve in cash.  These
    // fields bound how many times the runner may be re-invoked inside the
    // bounded window while keeping the day terminal once the sleeve aligns.
    private static string simulationCycleAttemptDate = "";
    private static int simulationCycleAttemptsToday = 0;
    private const int MaxSimulationCycleAttemptsPerSession = 30;
    private static DateTime nextCloseShadowAttempt = DateTime.MinValue;
    private static DateTime nextLakeAttempt = DateTime.MinValue;
    private static DateTime nextExecutionAttempt = DateTime.MinValue;
    // Hourly read-only account/position snapshot. Both profiles keep this job
    // because it performs no broker call and never enables execution.
    private static string lastHourlySnapshotHour = "";
    private static DateTime nextHourlySnapshotAttempt = DateTime.MinValue;
    // Bridge running evidence (the live strategy plus the Redis RPC version it
    // answers with) is recorded once per day.  Both profiles keep this job: it
    // is one read-only ping plus local file reads and never touches the order
    // path.
    private static string lastBridgeDailyRecordDate = "";
    private static DateTime nextBridgeDailyRecordAttempt = DateTime.MinValue;
    // Snapshot freshness is display-only.  It refreshes on a slower cadence
    // than the tray timer because the persisted snapshot only changes hourly,
    // and an aged snapshot must never repaint the account state icon: the live
    // Bridge ping, not this age, is the liveness authority.
    private static string snapshotFreshnessText = "快照 未知";
    private static DateTime nextSnapshotFreshnessAttempt = DateTime.MinValue;
    // Facts-only Host Agent delivery is deliberately separate from the
    // simulation order scheduler.  It never changes the account state/icon.
    private static DateTime nextFactDeliveryAttempt = DateTime.MinValue;
    private static DateTime nextStrategyDeploymentAttempt = DateTime.MinValue;
    private static string lastStrategyDeploymentState = "";

    [STAThread]
    private static void Main()
    {
        LoadRuntimeNodeConfig();
        Account = LoadConfiguredAccount();
        mutex = new MutexHandle("Local\\KitlingBigQMTNativeTray-" + Profile);
        if (!mutex.IsFirstInstance) return;
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        ContextMenuStrip menu = new ContextMenuStrip();
        statusItem = new ToolStripMenuItem(ProfileTitle + " " + Account + "：状态加载中");
        statusItem.Enabled = false;
        menu.Items.Add(statusItem);
        qmtItem = new ToolStripMenuItem("QMT：检查中（PROCESS ONLY）"); qmtItem.Enabled = false; menu.Items.Add(qmtItem);
        miniQmtItem = new ToolStripMenuItem("MiniQMT：检查中（免密服务）"); miniQmtItem.Enabled = false; menu.Items.Add(miniQmtItem);
        redisItem = new ToolStripMenuItem("Redis：检查中"); redisItem.Enabled = false; menu.Items.Add(redisItem);
        bridgeItem = new ToolStripMenuItem("Bridge：" + bridgeState); bridgeItem.Enabled = false; menu.Items.Add(bridgeItem);
        dashboardItem = new ToolStripMenuItem("Dashboard：检查中"); dashboardItem.Enabled = false; menu.Items.Add(dashboardItem);
        coordinatorItem = new ToolStripMenuItem("Coordinator：检查中（只读）"); coordinatorItem.Enabled = false; menu.Items.Add(coordinatorItem);
        intentItem = new ToolStripMenuItem("Intents：检查中（只读预览）"); intentItem.Enabled = false; menu.Items.Add(intentItem);
        hostAgentItem = new ToolStripMenuItem("Host Agent：初始化中（只读）"); hostAgentItem.Enabled = false; menu.Items.Add(hostAgentItem);
        strategyDeploymentItem = new ToolStripMenuItem("策略部署：未同步（安装不启动）"); strategyDeploymentItem.Enabled = false; menu.Items.Add(strategyDeploymentItem);
        menu.Items.Add(new ToolStripSeparator());
        ToolStripMenuItem services = new ToolStripMenuItem("服务管理");
        services.DropDownItems.Add("启动缺失的 QMT", null, delegate { StartQmt(false); });
        services.DropDownItems.Add("重启本账户 QMT", null, delegate { StartQmt(true); });
        services.DropDownItems.Add("启动缺失的 MiniQMT（免密）", null, delegate { StartMiniQmt(); });
        services.DropDownItems.Add("停止 MiniQMT（仅此账户）", null, delegate { StopMiniQmt(); });
        services.DropDownItems.Add("启动缺失的 Redis", null, delegate { StartRedis(); });
        services.DropDownItems.Add("确保本地看板运行", null, delegate { EnsureDashboard(); });
        services.DropDownItems.Add("立即探测 Bridge（只读）", null, delegate { ProbeBridge(); });
        services.DropDownItems.Add("立即同步 Host Agent（只读）", null, delegate { HostAgentSyncNow(); });
        services.DropDownItems.Add("立即拉取策略安装请求（不启动）", null, delegate { StrategyDeploymentIfDue(DateTime.Now, true); });
        menu.Items.Add(services);
        menu.Items.Add("打开看板", null, delegate { OpenDashboard(); });
        menu.Items.Add("打开本账户日志", null, delegate { OpenLogs(); });
        menu.Items.Add("生成诊断报告", null, delegate { GenerateDiagnosis(); });
        windowsStartupItem = new ToolStripMenuItem("随 Windows 启动此托盘");
        windowsStartupItem.CheckOnClick = true;
        windowsStartupItem.CheckedChanged += delegate { SetWindowsStartup(windowsStartupItem.Checked); };
        menu.Items.Add(windowsStartupItem);
        if (Profile == "simulation")
        {
            // One checkable row per installed strategy, rebuilt when the
            // installed set changes (see RebuildStrategyPolicyMenu).
            strategyPolicyMenu = new ToolStripMenuItem("策略运行开关");
            menu.Items.Add(strategyPolicyMenu);
        }
        else
        {
            strategyPolicyItem = new ToolStripMenuItem("允许已批准正式策略恢复意图");
            strategyPolicyItem.CheckOnClick = true;
            strategyPolicyItem.CheckedChanged += delegate { SetStrategyPolicy(strategyPolicyItem.Checked); };
            menu.Items.Add(strategyPolicyItem);
        }
        if (Profile == "simulation")
            menu.Items.Add("删除已安装策略（需要密码）", null, delegate { UninstallInstalledStrategies(); });
        menu.Items.Add("刷新全部状态", null, delegate { RefreshStatus(); });
        menu.Items.Add("锁定订单状态", null, delegate { LockReminder(); });
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("退出托盘", null, delegate { Application.Exit(); });

        tray = new NotifyIcon();
        // The executable is compiled with the profile-specific .ico resource.
        // Use that resource for the notification area as well; SystemIcons
        // would otherwise hide the blue S / deep-blue P account identity.
        try
        {
            trayIcon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            tray.Icon = trayIcon ?? SystemIcons.Information;
        }
        catch
        {
            tray.Icon = SystemIcons.Information;
        }
        tray.Text = ProfileTitle + " " + Account + "｜状态加载中";
        tray.ContextMenuStrip = menu;
        tray.Visible = true;
        tray.DoubleClick += delegate { OpenDashboard(); };
        Application.ApplicationExit += delegate { tray.Visible = false; if (trayIcon != null) trayIcon.Dispose(); Audit("tray_stopped", "user_exit"); mutex.Dispose(); };
        Audit("tray_started", "native_dotnet_one_account_exe; host_agent_embedded=true; read_only");
        windowsStartupItem.Checked = WindowsStartupEnabled();
        if (Profile == "simulation") RebuildStrategyPolicyMenu();
        else strategyPolicyItem.Checked = StrategyPolicyEnabled();
        RefreshStatus();
        Timer timer = new Timer();
        timer.Interval = 30000;
        timer.Tick += delegate { RefreshStatus(); TryRunScheduler(); };
        timer.Start();
        Application.Run();
    }

    private static string RootPath()
    {
        return Directory.GetParent(Application.StartupPath).FullName;
    }

    private static System.Collections.Generic.Dictionary<string, object> LoadMachineLocal()
    {
        try
        {
            string path = Path.Combine(RootPath(), "config", "machine.local.json");
            if (!File.Exists(path)) return new System.Collections.Generic.Dictionary<string, object>();
            object root = new JavaScriptSerializer().DeserializeObject(File.ReadAllText(path, Encoding.UTF8));
            return root as System.Collections.Generic.Dictionary<string, object>
                ?? new System.Collections.Generic.Dictionary<string, object>();
        }
        catch { return new System.Collections.Generic.Dictionary<string, object>(); }
    }

    private static string NestedConfigString(System.Collections.Generic.Dictionary<string, object> root, string section, string key)
    {
        object sectionValue;
        if (!root.TryGetValue(section, out sectionValue)) return "";
        var sectionMap = sectionValue as System.Collections.Generic.Dictionary<string, object>;
        if (sectionMap == null) return "";
        object value;
        return sectionMap.TryGetValue(key, out value) && value != null ? Convert.ToString(value).Trim() : "";
    }

    private static void LoadRuntimeNodeConfig()
    {
        var machine = LoadMachineLocal();
        configuredHostId = NestedConfigString(machine, "coordinator", "host_id");
        configuredCoordinatorEndpoint = NestedConfigString(machine, "coordinator", "endpoint");
        configuredFactSecretPath = NestedConfigString(machine, "host_agent", "fact_secret_path");
        if (configuredHostId.Length == 0) configuredHostId = "192.0.2.105";
        if (configuredCoordinatorEndpoint.Length == 0) configuredCoordinatorEndpoint = "http://192.0.2.121:18443";
    }

    private static string HostId()
    {
        return configuredHostId.Length == 0 ? "192.0.2.105" : configuredHostId;
    }

    private static string ShadowCoordinatorEndpoint()
    {
        try
        {
            Uri uri = new Uri(configuredCoordinatorEndpoint);
            UriBuilder builder = new UriBuilder(uri);
            builder.Port = 18666;
            builder.Path = "/api/v1/facts/ingest";
            builder.Query = "";
            return builder.Uri.ToString();
        }
        catch { return "http://192.0.2.121:18666/api/v1/facts/ingest"; }
    }

    private static string FactSecretPath()
    {
        string configured = configuredFactSecretPath;
        if (configured.Length > 0)
        {
            configured = Environment.ExpandEnvironmentVariables(configured);
            if (!Path.IsPathRooted(configured)) configured = Path.Combine(RootPath(), configured);
            if (File.Exists(configured)) return configured;
        }
        string safeHost = HostId().Replace('.', '_').Replace(':', '_').Replace('/', '_');
        string shortHost = safeHost;
        int lastSeparator = safeHost.LastIndexOf('_');
        if (lastSeparator >= 0 && lastSeparator + 1 < safeHost.Length) shortHost = safeHost.Substring(lastSeparator + 1);
        string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "Kitling", "BigQMT");
        string[] candidates = new string[] {
            Path.Combine(root, "host-facts", "host-" + safeHost + "-fact-shadow.json"),
            Path.Combine(root, "host-facts", "host-" + shortHost + "-fact-shadow-20260917.json"),
            Path.Combine(root, "secrets", "host-" + safeHost + "-fact-shadow.json"),
            Path.Combine(root, "secrets", "host-" + shortHost + "-fact-shadow.json")
        };
        foreach (string candidate in candidates) if (File.Exists(candidate)) return candidate;
        return candidates[0];
    }

    private static string LoadConfiguredAccount()
    {
        // The public source contains synthetic account IDs only.  A deployed
        // host may override the profile account in the ignored local config;
        // this keeps the native tray, Redis RPC namespace and Coordinator
        // heartbeat on the same account without publishing broker identifiers.
        try
        {
            string path = Path.Combine(RootPath(), "config", "machine.local.json");
            if (!File.Exists(path)) return DefaultAccount;
            string json = File.ReadAllText(path, Encoding.UTF8);
            JavaScriptSerializer serializer = new JavaScriptSerializer();
            object root = serializer.DeserializeObject(json);
            var rootMap = root as System.Collections.Generic.Dictionary<string, object>;
            object environments;
            if (rootMap == null || !rootMap.TryGetValue("environments", out environments)) return DefaultAccount;
            var envMap = environments as System.Collections.Generic.Dictionary<string, object>;
            object profileNode;
            if (envMap == null || !envMap.TryGetValue(Profile, out profileNode)) return DefaultAccount;
            var profileMap = profileNode as System.Collections.Generic.Dictionary<string, object>;
            object account;
            if (profileMap == null || !profileMap.TryGetValue("account_id", out account)) return DefaultAccount;
            string value = Convert.ToString(account);
            return string.IsNullOrWhiteSpace(value) ? DefaultAccount : value.Trim();
        }
        catch
        {
            // A malformed local override must not stop the status tray.  The
            // Python preflight remains responsible for rejecting bad config.
            return DefaultAccount;
        }
    }

    // The msys2 build of redis-server.exe understands POSIX-style mount paths
    // such as /cygdrive/f/... but misinterprets a raw Windows "F:\..." argument
    // as a relative path under the current directory. Convert drive paths so the
    // auto-restart and menu launcher use the same form as a verified manual start.
    private static string ToMsysPath(string windowsPath)
    {
        if (string.IsNullOrEmpty(windowsPath)) return windowsPath;
        string p = windowsPath.Replace('\\', '/');
        if (p.Length >= 2 && p[1] == ':')
            return "/cygdrive/" + char.ToLowerInvariant(p[0]) + p.Substring(2);
        return p;
    }

    // The checked-in Redis templates intentionally use a neutral historical
    // root so they are safe to publish.  Before starting Redis on a host,
    // materialize a local config with the actual project root.  This keeps a
    // migrated tray independent of C:\BigQMT and avoids the MSYS2 path/config
    // failure that previously left the tray red after auto-repair.
    private static string PrepareRedisConfig()
    {
        string template = Path.Combine(RootPath(), "config", "redis",
            Profile == "simulation" ? "redis-simulation.conf" : "redis-production.conf");
        string directory = Path.Combine(RootPath(), "runtime_data", "redis", Profile);
        Directory.CreateDirectory(directory);
        string materialized = Path.Combine(directory, "redis-autostart.conf");
        string root = ToMsysPath(RootPath());
        string text = File.ReadAllText(template, Encoding.UTF8)
            .Replace("C:/BigQMT/work/kitling_bigqmt", root)
            .Replace("C:\\BigQMT\\work\\kitling_bigqmt", root);
        File.WriteAllText(materialized, text, new UTF8Encoding(false));
        return materialized;
    }

    private static void StartRedisProcess()
    {
        string config = PrepareRedisConfig();
        string exe = Path.Combine(RootPath(), "runtime_data", "redis", "_package_inspect",
            "Redis-8.10.1-Windows-x64-msys2", "redis-server.exe");
        ProcessStartInfo info = new ProcessStartInfo();
        info.FileName = exe;
        info.Arguments = "\"" + ToMsysPath(config) + "\"";
        info.WorkingDirectory = RootPath();
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        Process.Start(info);
    }

    private static bool TcpAvailable(int port)
    {
        try
        {
            using (TcpClient client = new TcpClient())
            {
                IAsyncResult result = client.BeginConnect("127.0.0.1", port, null, null);
                bool connected = result.AsyncWaitHandle.WaitOne(700);
                if (!connected) return false;
                client.EndConnect(result);
                return true;
            }
        }
        catch { return false; }
    }

    private static bool DashboardAvailable()
    {
        try
        {
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + DashboardPort + "/healthz");
            request.Timeout = 1200;
            request.ReadWriteTimeout = 1200;
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse()) return response.StatusCode == HttpStatusCode.OK;
        }
        catch { return false; }
    }

    private static void RefreshStatus()
    {
        bool redis = TcpAvailable(RedisPort);
        bool dashboard = DashboardAvailable();
        string qmt = QmtStatus();
        string miniQmt = MiniQmtStatus();
        RefreshBridgeProbe(qmt);
        string runtimeHealth = RuntimeHealth();
        string snapshotFreshness = SnapshotFreshness();
        // The persisted Bridge snapshot is diagnostic evidence and may be old
        // after a QMT restart.  The live, allow-listed ping is the current
        // liveness authority; do not paint a healthy account red merely
        // because an older snapshot has aged out.
        string state = redis && dashboard && qmt == "RUNNING" && miniQmt == "RUNNING" && bridgeLiveHealthy ? "在线" : "降级";
        string detail = "Redis " + (redis ? "正常" : "不可达")
            + "｜看板 " + (dashboard ? "正常" : "不可达")
            + "｜" + snapshotFreshness
            + "｜订单锁定";
        statusItem.Text = ProfileTitle + " " + Account + "：" + state + "（" + detail + "）";
        qmtItem.Text = "QMT：" + (qmt == "RUNNING" ? "运行中（Bridge Ping 为账户链路证明）" : "未运行（将自动补拉）");
        miniQmtItem.Text = "MiniQMT：" + (miniQmt == "RUNNING" ? "运行中（免密，PROCESS ONLY）" : "未运行（将自动补拉）");
        redisItem.Text = "Redis：" + (redis ? "正常" : "不可达（将自动补拉）") + "（端口 " + RedisPort + "）";
        bridgeItem.Text = "Bridge：" + bridgeState + "｜快照 " + runtimeHealth;
        dashboardItem.Text = "Dashboard：" + (dashboard ? "正常" : "不可达（将自动补拉）") + "（端口 " + DashboardPort + "）";
        hostAgentItem.Text = "Host Agent：" + hostAgentState + "｜" + HostId() + "｜" + hostAgentDetail;
        if (strategyDeploymentItem != null && lastStrategyDeploymentState.Length > 0)
            strategyDeploymentItem.Text = "策略部署：" + lastStrategyDeploymentState + "（安装不启动）";
        if (Profile == "simulation") RebuildStrategyPolicyMenu();
        RefreshCoordinatorPreview();
        RefreshCoordinatorIntentPreview();
        string tip = ProfileTitle + " " + Account + "｜" + state;
        tray.Text = tip.Substring(0, Math.Min(63, tip.Length));
        SetIcon(state);
        SendCoordinatorHeartbeat(qmt, miniQmt, redis, dashboard);
        hostAgentItem.Text = "Host Agent：" + hostAgentState + "｜" + HostId() + "｜" + hostAgentDetail;
        Audit("status_refreshed", state + "; " + detail);
        AutoStartMissingQmt(qmt);
        AutoStartMissingMiniQmt(miniQmt);
        AutoStartMissingRedis(redis);
        AutoStartMissingDashboard(dashboard);
    }

    private static void RefreshBridgeProbe(string qmt)
    {
        if (qmt != "RUNNING")
        {
            bridgeLiveHealthy = false;
            bridgeState = "等待 QMT 登录（只读）";
            return;
        }
        if (DateTime.UtcNow < nextBridgeProbeAttempt) return;
        nextBridgeProbeAttempt = DateTime.UtcNow.AddMinutes(1);
        bool ok;
        string output = RunPython("check_bridge_ping.py", "--profile " + Profile + " --timeout 3", 6000, out ok);
        bridgeLiveHealthy = ok && output.IndexOf("\"status\": \"PASS\"") >= 0;
        bridgeState = bridgeLiveHealthy ? "通过（自动只读 Ping）" : "降级/不可达（自动只读探测）";
        Audit("bridge_auto_probe", bridgeLiveHealthy ? "PASS" : output);
    }

    private static void SendCoordinatorHeartbeat(string qmt, string miniQmt, bool redis, bool dashboard)
    {
        // Coordinator receives a sanitized read-only service snapshot only.
        // The helper has no QMT, Redis, credential, order or shell interface.
        string signature = qmt + "/" + miniQmt + "/" + redis + "/" + dashboard + "/" + bridgeLiveHealthy;
        bool ok;
        string output = RunPython(
            "send_host_agent_heartbeat.py",
            "--profile " + Profile
            + " --qmt " + (qmt == "RUNNING" ? "UP" : "DOWN")
            + " --miniqmt " + (miniQmt == "RUNNING" ? "UP" : "DOWN")
            + " --redis " + (redis ? "UP" : "DOWN")
            + " --bridge " + (bridgeLiveHealthy ? "UP" : "DOWN")
            + " --dashboard " + (dashboard ? "UP" : "DOWN"),
            6000,
            out ok
        );
        if (ok)
        {
            hostAgentState = "心跳正常";
            hostAgentDetail = "只读服务已上报";
        }
        else
        {
            hostAgentState = "心跳失败";
            hostAgentDetail = "Coordinator不可达，继续本地运行";
        }
        if (!ok || signature != lastCoordinatorHeartbeatState)
            Audit("coordinator_heartbeat", ok ? "accepted; " + signature : output);
        lastCoordinatorHeartbeatState = signature;
    }

    private static void HostAgentSyncNow()
    {
        // Keep the menu responsive: the facts-only uploader may wait on a
        // network timeout.  It never has an order, lease, QMT or Redis write
        // path, and the normal 5-minute scheduler remains unchanged.
        System.Threading.ThreadPool.QueueUserWorkItem(delegate
        {
            try
            {
                nextFactDeliveryAttempt = DateTime.MinValue;
                HostFactDeliveryIfDue(DateTime.Now);
                Audit("host_agent_manual_sync", hostAgentState + "; " + hostAgentDetail);
            }
            catch (Exception error)
            {
                hostAgentState = "同步异常";
                hostAgentDetail = error.GetType().Name;
                Audit("host_agent_manual_sync_error", error.GetType().Name + ": " + error.Message);
            }
        });
    }

    private static void StrategyDeploymentIfDue(DateTime now, bool manual)
    {
        if (!manual && now < nextStrategyDeploymentAttempt) return;
        nextStrategyDeploymentAttempt = now.AddSeconds(30);
        bool ok;
        string output = RunPython("poll_strategy_deployments.py", "--once", 45000, out ok);
        string state;
        int localInstalled = LocalInstalledCount();
        if (localInstalled > 0)
        {
            state = "已安装（未启动）; 本地 " + localInstalled + " 条";
        }
        else if (output.IndexOf("\"status\": \"ok\"") >= 0)
        {
            int marker = output.IndexOf("\"deployments\":", StringComparison.Ordinal);
            if (marker >= 0) state = "无待安装请求; 本地无安装";
            else state = "拉取完成; 本地无安装";
        }
        else if (output.IndexOf("library_root is not configured", StringComparison.OrdinalIgnoreCase) >= 0)
        {
            state = "等待本机策略库配置";
        }
        else
        {
            state = "拉取失败（保留订单锁）";
        }
        if (manual || state != lastStrategyDeploymentState)
            Audit("strategy_deployment_poll", state + "; orders_enabled=false; run_after_install=false");
        lastStrategyDeploymentState = state;
        if (strategyDeploymentItem != null)
            strategyDeploymentItem.Text = "策略部署：" + state + "（安装不启动）";
        // Hide the strategy run toggles when nothing is installed: the
        // toggles are meaningless without a deployed strategy to run.
        if (Profile == "simulation" && strategyPolicyMenu != null)
            strategyPolicyMenu.Visible = localInstalled > 0;
        else if (strategyPolicyItem != null)
            strategyPolicyItem.Visible = true;
    }

    private static int LocalInstalledCount()
    {
        bool ok;
        string output = RunPython("uninstall_strategy_package.py", "--list", 15000, out ok);
        if (!ok) return 0;
        // Avoid System.Web.Script.Serialization quirks: count "strategy_id"
        // occurrences inside the JSON returned by --list.  Each installed
        // entry contributes exactly one such key, so this is a stable
        // approximation and matches the on-disk truth regardless of how the
        // serializer shapes nested arrays.
        int count = 0; int index = 0;
        while ((index = output.IndexOf("\"strategy_id\"", index, StringComparison.Ordinal)) >= 0)
        {
            count++; index += "\"strategy_id\"".Length;
        }
        return count;
    }

    private static void RefreshCoordinatorPreview()
    {
        // Display only the Coordinator's read-only candidate/lease projection.
        // This method never asks for, renews or releases an execution lease.
        bool ok;
        string output = RunPython("check_coordinator_lease_preview.py", "--profile " + Profile + " --timeout 3", 5000, out ok);
        if (!ok || output.IndexOf("\"status\": \"PASS\"") < 0)
        {
            coordinatorItem.Text = "Coordinator：不可达｜执行权锁定";
            return;
        }
        bool active = output.IndexOf("\"lease_state\": \"ACTIVE\"") >= 0;
        bool candidate = output.IndexOf("\"candidate_eligible\": true") >= 0;
        if (active)
            coordinatorItem.Text = "Coordinator：本机 ACTIVE 租约（仍需本机订单门禁）";
        else if (candidate)
            coordinatorItem.Text = "Coordinator：模拟执行候选（未分配，订单锁定）";
        else
            coordinatorItem.Text = "Coordinator：只读／不可执行";
    }

    private static void RefreshCoordinatorIntentPreview()
    {
        // Read-only audit of the Coordinator typed-intent preview.  The probe
        // issues exactly one authenticated GET and can never submit, lease,
        // confirm or execute an intent.  A failure downgrades this single
        // informational line only; it never changes the account state icon.
        bool ok;
        string output = RunPython("probe_host_agent_intent_preview.py", "--account-id " + Account + " --timeout 3", 5000, out ok);
        string signature;
        if (!ok || output.IndexOf("\"status\": \"passed\"") < 0)
        {
            intentItem.Text = "Intents：预览不可达（只读，订单锁定）";
            signature = "unreachable";
        }
        else if (output.IndexOf("\"intent_count\": 0") >= 0)
        {
            intentItem.Text = "Intents：空预览／无待执行意图（订单锁定）";
            signature = "empty_readonly";
        }
        else
        {
            intentItem.Text = "Intents：非空预览（本机拒绝执行，订单锁定）";
            signature = "non_empty_rejected";
        }
        // Audit only on change so a healthy account does not flood the log.
        if (signature != lastCoordinatorIntentState)
            Audit("coordinator_intent_preview", signature + "; readonly=true; orders_enabled=false");
        lastCoordinatorIntentState = signature;
    }

    private static string QmtStatus()
    {
        bool ok;
        string output = RunPython("qmt_launcher_cli.py", "status --profile " + Profile, 4000, out ok);
        if (!ok || output.IndexOf("\"status\":\"RUNNING\"") < 0) return "STOPPED";
        return "RUNNING";
    }

    private static string RuntimeHealth()
    {
        bool ok;
        string output = RunPython("check_tray_health.py", "--profile " + Profile + " --port " + DashboardPort + " --attempts 1", 5000, out ok);
        if (output.IndexOf("\"overall\": \"HEALTHY\"") >= 0) return "HEALTHY";
        if (output.IndexOf("\"overall\": \"DEGRADED\"") >= 0) return "DEGRADED";
        return ok ? "UNKNOWN" : "UNAVAILABLE";
    }

    private static string SnapshotFreshness()
    {
        // Show the age of the persisted account snapshot in the status line so
        // a stalled hourly scheduler is visible in the tray itself instead of
        // only in a separate health check.  Read-only probe: it never calls QMT
        // or Redis and it never changes the order lock.
        if (DateTime.UtcNow < nextSnapshotFreshnessAttempt) return snapshotFreshnessText;
        nextSnapshotFreshnessAttempt = DateTime.UtcNow.AddSeconds(60);
        bool ok;
        string output = RunPython("check_snapshot_freshness.py", "--profile " + Profile, 8000, out ok);
        string age = JsonString(output, "age_text");
        string limit = JsonString(output, "max_age_text");
        if (age.Length > 0 && output.IndexOf("\"status\": \"PASS\"") >= 0)
            snapshotFreshnessText = "快照 " + age + "（上限 " + limit + "）";
        else if (age.Length > 0)
            snapshotFreshnessText = "快照 " + age + "（已超上限 " + limit + "）";
        else if (output.IndexOf("no persisted Bridge snapshot") >= 0)
            snapshotFreshnessText = "快照 缺失（尚无持久化快照）";
        else if (!ok)
            snapshotFreshnessText = "快照 不可测（探测失败）";
        else
            snapshotFreshnessText = "快照 未知（" + JsonString(output, "detail") + "）";
        return snapshotFreshnessText;
    }

    private static string JsonString(string payload, string key)
    {
        // Minimal reader for one flat JSON string field.  The tray only ever
        // inspects its own read-only probe output, and this single-file
        // executable deliberately avoids taking on a JSON dependency.
        if (payload == null) return "";
        string needle = "\"" + key + "\": \"";
        int start = payload.IndexOf(needle, StringComparison.Ordinal);
        if (start < 0) return "";
        start += needle.Length;
        int end = payload.IndexOf('"', start);
        return end < 0 ? "" : payload.Substring(start, end - start);
    }

    private static string MiniQmtStatus()
    {
        bool ok;
        string output = RunPython("miniqmt_launcher_cli.py", "status --profile " + Profile, 4000, out ok);
        return ok && output.IndexOf("\"status\":\"RUNNING\"") >= 0 ? "RUNNING" : "STOPPED";
    }

    private static void AutoStartMissingQmt(string qmt)
    {
        if (qmt != "STOPPED" || DateTime.UtcNow < nextAutoQmtAttempt) return;
        nextAutoQmtAttempt = DateTime.UtcNow.AddMinutes(2);
        bool ok;
        string output = RunPython("qmt_launcher_cli.py", "open --profile " + Profile, 15000, out ok);
        Audit("qmt_auto_start_login", ok ? "requested" : output);
    }

    private static void AutoStartMissingMiniQmt(string miniQmt)
    {
        if (miniQmt != "STOPPED" || DateTime.UtcNow < nextAutoMiniQmtAttempt) return;
        nextAutoMiniQmtAttempt = DateTime.UtcNow.AddMinutes(2);
        bool ok;
        string output = RunPython("miniqmt_launcher_cli.py", "open --profile " + Profile, 8000, out ok);
        Audit("miniqmt_auto_start_linkmini", ok ? "requested" : output);
    }

    private static void AutoStartMissingRedis(bool redis)
    {
        if (redis || DateTime.UtcNow < nextAutoRedisAttempt) return;
        nextAutoRedisAttempt = DateTime.UtcNow.AddMinutes(2);
        try
        {
            string exe = Path.Combine(RootPath(), "runtime_data", "redis", "_package_inspect", "Redis-8.10.1-Windows-x64-msys2", "redis-server.exe");
            if (!File.Exists(exe)) { Audit("redis_auto_start_error", "missing redis-server: " + exe); return; }
            StartRedisProcess();
            Audit("redis_auto_start_requested", Profile);
        }
        catch (Exception error) { Audit("redis_auto_start_error", error.GetType().Name + ": " + error.Message); }
    }

    private static void AutoStartMissingDashboard(bool dashboard)
    {
        if (dashboard || DateTime.UtcNow < nextAutoDashboardAttempt) return;
        nextAutoDashboardAttempt = DateTime.UtcNow.AddMinutes(2);
        try
        {
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = "py.exe";
            info.Arguments = "-3.12 \"" + Path.Combine(RootPath(), "scripts", "run_local_dashboard.py") + "\" --port " + DashboardPort + " --profile " + Profile;
            info.WorkingDirectory = RootPath();
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            Process.Start(info);
            Audit("dashboard_auto_start_requested", DashboardPort.ToString());
        }
        catch (Exception error) { Audit("dashboard_auto_start_error", error.GetType().Name + ": " + error.Message); }
    }

    private static string RunPython(string scriptName, string arguments, int timeout, out bool ok)
    {
        ok = false;
        try
        {
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = "py.exe";
            info.Arguments = "-3.12 \"" + Path.Combine(RootPath(), "scripts", scriptName) + "\" " + arguments;
            info.WorkingDirectory = RootPath(); info.UseShellExecute = false; info.CreateNoWindow = true;
            info.RedirectStandardOutput = true; info.RedirectStandardError = true;
            using (Process process = Process.Start(info))
            {
                string stdout = process.StandardOutput.ReadToEnd(); string stderr = process.StandardError.ReadToEnd();
                if (!process.WaitForExit(timeout)) { try { process.Kill(); } catch { } return stdout + stderr; }
                ok = process.ExitCode == 0; return stdout + stderr;
            }
        }
        catch (Exception error) { return error.GetType().Name + ": " + error.Message; }
    }

    private static void SetIcon(string state)
    {
        // Account colors stay stable: simulation uses sky blue and the
        // production-readonly account uses deep blue.  Deep red is reserved
        // exclusively for a degraded runtime state.
        Color color = state == "在线" ? Color.FromArgb(50, 169, 232) : Color.FromArgb(145, 25, 35);
        if (Profile != "simulation" && state == "在线") color = Color.FromArgb(20, 58, 122);
        Bitmap bitmap = new Bitmap(32, 32);
        using (Graphics graphics = Graphics.FromImage(bitmap))
        {
            graphics.Clear(Color.Transparent);
            using (Brush brush = new SolidBrush(color)) graphics.FillEllipse(brush, new Rectangle(1, 1, 30, 30));
            using (Font font = new Font("Segoe UI", 19, FontStyle.Bold, GraphicsUnit.Pixel))
            using (StringFormat format = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
                graphics.DrawString(Profile == "simulation" ? "S" : "P", font, Brushes.White, new RectangleF(0, 0, 32, 32), format);
        }
        trayIcon = Icon.FromHandle(bitmap.GetHicon());
        tray.Icon = trayIcon;
    }

    private static void OpenDashboard()
    {
        Process.Start("http://127.0.0.1:" + DashboardPort + DashboardRoute);
        Audit("dashboard_opened", "read_only");
    }

    private static void OpenLogs()
    {
        string directory = Path.Combine(RootPath(), "runtime_data", "audit", Profile);
        Directory.CreateDirectory(directory);
        Process.Start("explorer.exe", "\"" + directory + "\"");
        Audit("logs_opened", directory);
    }

    private static void StartQmt(bool restart)
    {
        if (restart && MessageBox.Show("仅重启本账户的 QMT 终端？不会改变订单锁。", ProfileTitle, MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;
        bool ok; string output = RunPython("qmt_launcher_cli.py", (restart ? "restart" : "open") + " --profile " + Profile, restart ? 15000 : 8000, out ok);
        MessageBox.Show(ok ? "QMT 请求已提交。请在 QMT 完成登录后刷新 Bridge。" : "QMT 请求失败：\n" + output, ProfileTitle, MessageBoxButtons.OK, ok ? MessageBoxIcon.Information : MessageBoxIcon.Warning);
        Audit(restart ? "qmt_restart_requested" : "qmt_start_requested", ok ? "accepted" : output); RefreshStatus();
    }

    private static void StartMiniQmt()
    {
        bool ok; string output = RunPython("miniqmt_launcher_cli.py", "open --profile " + Profile, 8000, out ok);
        MessageBox.Show(ok ? "MiniQMT 免密启动请求已提交。" : "MiniQMT 启动失败：\n" + output, ProfileTitle, MessageBoxButtons.OK, ok ? MessageBoxIcon.Information : MessageBoxIcon.Warning);
        Audit("miniqmt_start_requested", ok ? "accepted" : output); RefreshStatus();
    }

    private static void StopMiniQmt()
    {
        if (MessageBox.Show("只停止此账户的 MiniQMT 及其 miniquote 子进程；不会停止大 QMT。继续？", ProfileTitle, MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;
        bool ok; string output = RunPython("miniqmt_launcher_cli.py", "close --profile " + Profile, 8000, out ok);
        MessageBox.Show(ok ? "MiniQMT 停止请求已提交。" : "MiniQMT 未能停止：\n" + output, ProfileTitle, MessageBoxButtons.OK, ok ? MessageBoxIcon.Information : MessageBoxIcon.Warning);
        Audit("miniqmt_stop_requested", ok ? "accepted" : output); RefreshStatus();
    }

    private static void StartRedis()
    {
        if (TcpAvailable(RedisPort)) { MessageBox.Show("Redis 已运行。", ProfileTitle); return; }
        string exe = Path.Combine(RootPath(), "runtime_data", "redis", "_package_inspect", "Redis-8.10.1-Windows-x64-msys2", "redis-server.exe");
        try { StartRedisProcess(); MessageBox.Show("Redis 启动请求已提交。", ProfileTitle); Audit("redis_start_requested", Profile); }
        catch (Exception error) { MessageBox.Show("Redis 无法启动：" + error.Message, ProfileTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning); Audit("redis_start_error", error.Message); }
    }

    private static void EnsureDashboard()
    {
        if (DashboardAvailable()) { MessageBox.Show("本地看板已运行。", ProfileTitle); return; }
        try
        {
            ProcessStartInfo info = new ProcessStartInfo("py.exe", "-3.12 \"" + Path.Combine(RootPath(), "scripts", "run_local_dashboard.py") + "\" --port " + DashboardPort + " --profile " + Profile);
            info.WorkingDirectory = RootPath(); info.UseShellExecute = false; info.CreateNoWindow = true; Process.Start(info);
            MessageBox.Show("看板启动请求已提交。", ProfileTitle); Audit("dashboard_start_requested", DashboardPort.ToString());
        }
        catch (Exception error) { MessageBox.Show("看板无法启动：" + error.Message, ProfileTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }

    private static void ProbeBridge()
    {
        bool ok; string output = RunPython("check_bridge_ping.py", "--profile " + Profile + " --timeout 3", 8000, out ok);
        bridgeLiveHealthy = ok && output.IndexOf("\"status\": \"PASS\"") >= 0;
        bridgeState = bridgeLiveHealthy ? "通过（只读 Ping）" : "降级/不可达（仅只读探测）";
        nextBridgeProbeAttempt = DateTime.UtcNow.AddMinutes(1);
        MessageBox.Show(bridgeState + "\n\n" + output, ProfileTitle + " Bridge", MessageBoxButtons.OK, ok ? MessageBoxIcon.Information : MessageBoxIcon.Warning);
        Audit("bridge_probe", bridgeState); RefreshStatus();
    }

    private static bool WindowsStartupEnabled()
    {
        using (RegistryKey key = Registry.CurrentUser.OpenSubKey("Software\\Microsoft\\Windows\\CurrentVersion\\Run", false))
        {
            return key != null && key.GetValue("BigQMTNativeTray-" + Profile, null) != null;
        }
    }

    private static void SetWindowsStartup(bool enabled)
    {
        try
        {
            using (RegistryKey key = Registry.CurrentUser.CreateSubKey("Software\\Microsoft\\Windows\\CurrentVersion\\Run"))
            {
                if (enabled) key.SetValue("BigQMTNativeTray-" + Profile, "\"" + Application.ExecutablePath + "\"");
                else key.DeleteValue("BigQMTNativeTray-" + Profile, false);
            }
            Audit("windows_startup", enabled ? "enabled" : "disabled");
        }
        catch (Exception error) { MessageBox.Show("Windows 启动项无法更新：" + error.Message, ProfileTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }

    private static bool StrategyPolicyEnabled()
    {
        // Production-only: the formal recovery intent flag.  Simulation uses
        // the per-strategy toggles instead (see StrategyAutoRunEnabled + the
        // dynamic 策略运行开关 submenu).
        try
        {
            string text = File.ReadAllText(Path.Combine(RootPath(), "config", "strategy_runtime_policy.json"), Encoding.UTF8);
            return text.IndexOf("\"strategy_recovery_enabled\": true") >= 0;
        }
        catch { return false; }
    }

    private static bool StrategyAutoRunEnabled(string strategyId)
    {
        // Local truth: simulation.strategies.<strategy_id>.auto_run_enabled.
        // Missing strategy or malformed config is fail-closed (false).
        try
        {
            string text = File.ReadAllText(Path.Combine(RootPath(), "config", "strategy_runtime_policy.json"), Encoding.UTF8);
            int idPos = text.IndexOf("\"" + strategyId + "\"", StringComparison.Ordinal);
            if (idPos < 0) return false;
            string window = text.Substring(idPos, Math.Min(180, text.Length - idPos));
            int flagPos = window.IndexOf("\"auto_run_enabled\"", StringComparison.Ordinal);
            if (flagPos < 0) return false;
            string snippet = window.Substring(flagPos, Math.Min(48, window.Length - flagPos));
            // JSON normalization writes ': true' / ': false'; only the true
            // form matches the substring below, keeping false fail-closed.
            return snippet.IndexOf(": true", StringComparison.Ordinal) >= 0
                || snippet.IndexOf(":true", StringComparison.Ordinal) >= 0;
        }
        catch { return false; }
    }

    private static void SetStrategyAutoRun(string strategyId, bool enabled)
    {
        bool ok; string output = RunPython("set_strategy_auto_run.py", "--strategy-id \"" + strategyId + "\" --enabled " + (enabled ? "true" : "false"), 5000, out ok);
        if (!ok)
        {
            MessageBox.Show("策略运行开关无法更新：\n" + output, ProfileTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            // Flip the checkbox back but suppress the CheckedChanged loopback.
            RebuildStrategyPolicyMenu();
            return;
        }
        Audit("strategy_policy", (enabled ? "enabled" : "disabled") + " " + strategyId);
    }

    private static System.Collections.Generic.List<string> lastPolicyMenuIds =
        new System.Collections.Generic.List<string>();
    private static bool policyMenuRebuilding = false;

    private static void RebuildStrategyPolicyMenu()
    {
        if (Profile != "simulation" || strategyPolicyMenu == null) return;
        System.Collections.Generic.List<string> ids = new System.Collections.Generic.List<string>();
        bool ok; string listed = RunPython("uninstall_strategy_package.py", "--list", 15000, out ok);
        if (ok)
        {
            // Collect installed strategy ids; an id that has no toggle keeps
            // whatever policy state it had (no write, no delete of entries).
            foreach (var entry in ParseInstalledEntries(listed))
                if (!ids.Contains(entry["strategy_id"])) ids.Add(entry["strategy_id"]);
        }
        bool same = ids.Count == lastPolicyMenuIds.Count;
        if (same) for (int i = 0; i < ids.Count; i++) if (ids[i] != lastPolicyMenuIds[i]) { same = false; break; }
        if (same) return; // no change, avoid flicker

        policyMenuRebuilding = true;
        try
        {
            strategyPolicyMenu.DropDownItems.Clear();
            if (ids.Count == 0)
            {
                ToolStripMenuItem empty = new ToolStripMenuItem("（无已安装策略）");
                empty.Enabled = false;
                strategyPolicyMenu.DropDownItems.Add(empty);
            }
            else
            {
                foreach (string id in ids)
                {
                    ToolStripMenuItem item = new ToolStripMenuItem("启用 " + id + " 自动运行");
                    item.CheckOnClick = true;
                    item.Checked = StrategyAutoRunEnabled(id);
                    string captured = id;
                    item.CheckedChanged += delegate
                    {
                        if (!policyMenuRebuilding) SetStrategyAutoRun(captured, item.Checked);
                    };
                    strategyPolicyMenu.DropDownItems.Add(item);
                }
            }
            lastPolicyMenuIds = new System.Collections.Generic.List<string>(ids);
        }
        finally { policyMenuRebuilding = false; }
    }

    private static void SetStrategyPolicy(bool enabled)
    {
        if (Profile != "simulation" && enabled && MessageBox.Show("这只记录正式策略恢复意图，不会开放正式下单。继续？", ProfileTitle, MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) { strategyPolicyItem.Checked = false; return; }
        bool ok; string output = RunPython("set_tray_strategy_policy.py", "--profile " + Profile + " --enabled " + (enabled ? "true" : "false"), 5000, out ok);
        if (!ok) { MessageBox.Show("策略开关无法更新：\n" + output, ProfileTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning); strategyPolicyItem.Checked = !enabled; return; }
        Audit("strategy_policy", enabled ? "enabled" : "disabled");
    }

    private static void UninstallInstalledStrategies()
    {
        string expectedHash = NestedConfigString(LoadMachineLocal(), "tray", "delete_strategy_password_sha256").ToLowerInvariant();
        if (expectedHash.Length != 64)
        {
            MessageBox.Show("未配置删除密码散列（tray.delete_strategy_password_sha256）。", ProfileTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            Audit("strategy_uninstall_blocked", "missing_password_hash");
            return;
        }
        string password;
        if (!PromptPassword("删除已安装策略", "输入托盘删除密码：", out password) || password.Length == 0)
        {
            Audit("strategy_uninstall_cancelled", "user_cancelled");
            return;
        }
        if (Sha256Hex(password) != expectedHash)
        {
            MessageBox.Show("密码错误。", ProfileTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            Audit("strategy_uninstall_blocked", "bad_password");
            return;
        }

        bool ok; string listed = RunPython("uninstall_strategy_package.py", "--list", 15000, out ok);
        if (!ok)
        {
            MessageBox.Show("无法列出已安装策略：\n" + listed, ProfileTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            Audit("strategy_uninstall_list_error", listed);
            return;
        }
        System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, string>> entries = ParseInstalledEntries(listed);
        if (entries.Count == 0)
        {
            MessageBox.Show("本机没有已安装策略。", ProfileTitle, MessageBoxButtons.OK, MessageBoxIcon.Information);
            Audit("strategy_uninstall_cancelled", "no_installs");
            return;
        }
        int[] selected = PromptStrategySelection(entries);
        if (selected == null)
        {
            Audit("strategy_uninstall_cancelled", "no_selection");
            return;
        }
        if (selected.Length == 0)
        {
            // The form refuses to close with 0 rows selected, so this is a
            // silent fallback only; never pop another dialog here.
            Audit("strategy_uninstall_cancelled", "empty_selection");
            return;
        }
        System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, string>> toDelete =
            new System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, string>>();
        foreach (int index in selected)
        {
            if (index >= 0 && index < entries.Count) toDelete.Add(entries[index]);
        }
        if (toDelete.Count == 0)
        {
            Audit("strategy_uninstall_cancelled", "empty_selection");
            return;
        }
        System.Text.StringBuilder preview = new System.Text.StringBuilder();
        foreach (var entry in toDelete)
        {
            preview.Append("  • ").Append(entry["strategy_id"]).Append("  ").Append(entry["version"]).Append("  ").Append(entry["build_id"]).Append("\n");
        }
        if (MessageBox.Show(
            "将永久删除本机以下 " + toDelete.Count + " 个已安装策略（不影响 NAS 候选库与 Coordinator 队列）：\n\n" +
            preview.ToString() +
            "\n确认继续？",
            ProfileTitle,
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Warning) != DialogResult.Yes)
        {
            Audit("strategy_uninstall_cancelled", "user_declined_confirmation");
            return;
        }

        int removed = 0; int missing = 0; System.Text.StringBuilder errors = new System.Text.StringBuilder();
        foreach (var entry in toDelete)
        {
            string args = "--strategy-id \"" + entry["strategy_id"] + "\" --version \"" + entry["version"] + "\" --build-id \"" + entry["build_id"] + "\"";
            bool itemOk; string output = RunPython("uninstall_strategy_package.py", args, 30000, out itemOk);
            if (output.IndexOf("\"status\": \"uninstalled\"") >= 0)
            {
                removed++;
                Audit("strategy_uninstalled", entry["strategy_id"] + " " + entry["version"] + " " + entry["build_id"] + "; orders_enabled=false; run_after_install=false");
                // Clear the per-strategy run switch so a deleted strategy is
                // also off in policy (fail-closed; a re-install starts disabled).
                if (Profile == "simulation")
                {
                    bool clearOk; string clearOut = RunPython("set_strategy_auto_run.py", "--strategy-id \"" + entry["strategy_id"] + "\" --clear", 5000, out clearOk);
                    if (clearOk) Audit("strategy_policy_cleared", entry["strategy_id"]);
                    else Audit("strategy_policy_clear_error", entry["strategy_id"] + ": " + clearOut);
                }
            }
            else if (output.IndexOf("\"status\": \"not_found\"") >= 0) { missing++; Audit("strategy_uninstall_missing", entry["strategy_id"] + " " + entry["version"] + " " + entry["build_id"]); }
            else
            {
                errors.Append(entry["strategy_id"]).Append(" → ").Append(output).Append("\n");
                Audit("strategy_uninstall_error", entry["strategy_id"] + ": " + output);
            }
        }
        string summary = "删除完成：成功 " + removed + " 条" + (missing > 0 ? "，目标已不存在 " + missing + " 条" : "") + (errors.Length > 0 ? "，失败 " + errors.Length + " 条" : "");
        MessageBox.Show(summary + (errors.Length > 0 ? "\n\n失败详情：\n" + errors.ToString() : ""), ProfileTitle, MessageBoxButtons.OK, MessageBoxIcon.Information);
        if (removed > 0 || missing > 0) RefreshLocalInstallMenuState();
    }

    private static System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, string>> ParseInstalledEntries(string listJson)
    {
        System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, string>> result =
            new System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, string>>();
        int arrayStart = listJson.IndexOf("\"installed\":", StringComparison.Ordinal);
        if (arrayStart < 0) return result;
        int arrayOpen = listJson.IndexOf('[', arrayStart);
        if (arrayOpen < 0) return result;
        int cursor = arrayOpen + 1;
        while (cursor < listJson.Length)
        {
            int objStart = listJson.IndexOf('{', cursor);
            if (objStart < 0) break;
            int objEnd = MatchClosingBrace(listJson, objStart);
            if (objEnd < 0) break;
            string entry = listJson.Substring(objStart, objEnd - objStart + 1);
            var map = new System.Collections.Generic.Dictionary<string, string>();
            foreach (string key in new[] { "strategy_id", "version", "build_id", "artifact_count" })
            {
                map[key] = ExtractJsonString(entry, key);
            }
            if (map["strategy_id"].Length > 0 && map["version"].Length > 0 && map["build_id"].Length > 0)
                result.Add(map);
            cursor = objEnd + 1;
        }
        return result;
    }

    private static void RefreshLocalInstallMenuState()
    {
        // Re-derive the strategy deployment menu text purely from the local
        // install_root.  This is what the user sees right after an uninstall,
        // before the next 30s Coordinator poll tick has run.
        int localInstalled = LocalInstalledCount();
        string state = localInstalled > 0
            ? "已安装（未启动）; 本地 " + localInstalled + " 条"
            : "无待安装请求; 本地无安装";
        lastStrategyDeploymentState = state;
        if (strategyDeploymentItem != null)
            strategyDeploymentItem.Text = "策略部署：" + state + "（安装不启动）";
        if (Profile == "simulation" && strategyPolicyMenu != null)
            strategyPolicyMenu.Visible = localInstalled > 0;
        else if (strategyPolicyItem != null)
            strategyPolicyItem.Visible = true;
        RebuildStrategyPolicyMenu();
        Audit("strategy_uninstall_menu_refreshed", state + "; orders_enabled=false; visible=" + (localInstalled > 0));
    }

    private static int[] PromptStrategySelection(System.Collections.Generic.List<System.Collections.Generic.Dictionary<string, string>> entries)
    {
        System.Collections.Generic.List<string> rows = new System.Collections.Generic.List<string>();
        foreach (var entry in entries)
        {
            rows.Add(entry["strategy_id"] + "\n    " + entry["version"] + "  " + entry["build_id"] + "  " +
                     "(" + (entry.ContainsKey("artifact_count") && entry["artifact_count"].Length > 0 ? entry["artifact_count"] : "?") + " 个产物)");
        }
        using (UninstallSelectionForm form = new UninstallSelectionForm(rows))
        {
            if (form.ShowDialog() != DialogResult.OK) return null;
            return form.SelectedIndicesCopy();
        }
    }

    private static bool PromptPassword(string title, string label, out string password)
    {
        password = "";
        using (PasswordPromptForm form = new PasswordPromptForm(title, label))
        {
            return form.ShowDialog() == DialogResult.OK && form.EnteredPassword(out password);
        }
    }

    private static int MatchClosingBrace(string text, int openIndex)
    {
        // Returns index of the '}' that balances text[openIndex] == '{',
        // honouring JSON string escapes so braces inside quoted values do
        // not confuse the matcher.
        int depth = 0;
        bool inString = false; bool escape = false;
        for (int i = openIndex; i < text.Length; i++)
        {
            char ch = text[i];
            if (inString)
            {
                if (escape) { escape = false; continue; }
                if (ch == '\\') { escape = true; continue; }
                if (ch == '"') inString = false;
                continue;
            }
            if (ch == '"') { inString = true; continue; }
            if (ch == '{') depth++;
            else if (ch == '}')
            {
                depth--;
                if (depth == 0) return i;
            }
        }
        return -1;
    }

    private static string ExtractJsonString(string json, string key)
    {
        // Find "key" : "value" with optional whitespace; decode the standard
        // JSON string escapes we care about.
        string needle = "\"" + key + "\"";
        int keyPos = json.IndexOf(needle, StringComparison.Ordinal);
        if (keyPos < 0) return "";
        int colon = json.IndexOf(':', keyPos + needle.Length);
        if (colon < 0) return "";
        int valueStart = colon + 1;
        while (valueStart < json.Length && (json[valueStart] == ' ' || json[valueStart] == '\t')) valueStart++;
        if (valueStart >= json.Length || json[valueStart] != '"') return "";
        int valueEnd = valueStart + 1;
        bool escape = false;
        while (valueEnd < json.Length)
        {
            char ch = json[valueEnd];
            if (escape) { escape = false; valueEnd++; continue; }
            if (ch == '\\') { escape = true; valueEnd++; continue; }
            if (ch == '"') break;
            valueEnd++;
        }
        if (valueEnd >= json.Length) return "";
        string raw = json.Substring(valueStart + 1, valueEnd - valueStart - 1);
        System.Text.StringBuilder builder = new System.Text.StringBuilder(raw.Length);
        for (int i = 0; i < raw.Length; i++)
        {
            char ch = raw[i];
            if (ch == '\\' && i + 1 < raw.Length)
            {
                char next = raw[i + 1];
                switch (next)
                {
                    case '"': builder.Append('"'); i++; break;
                    case '\\': builder.Append('\\'); i++; break;
                    case '/': builder.Append('/'); i++; break;
                    case 'b': builder.Append('\b'); i++; break;
                    case 'f': builder.Append('\f'); i++; break;
                    case 'n': builder.Append('\n'); i++; break;
                    case 'r': builder.Append('\r'); i++; break;
                    case 't': builder.Append('\t'); i++; break;
                    case 'u':
                        if (i + 5 < raw.Length)
                        {
                            int code;
                            if (int.TryParse(raw.Substring(i + 2, 4), System.Globalization.NumberStyles.HexNumber, System.Globalization.CultureInfo.InvariantCulture, out code))
                            {
                                builder.Append((char)code); i += 5;
                            }
                            else builder.Append(ch);
                        }
                        else builder.Append(ch);
                        break;
                    default: builder.Append(next); i++; break;
                }
            }
            else builder.Append(ch);
        }
        return builder.ToString();
    }

    private static string Sha256Hex(string text)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(text ?? "");
        byte[] hash;
        using (SHA256 sha = SHA256.Create()) hash = sha.ComputeHash(bytes);
        System.Text.StringBuilder builder = new System.Text.StringBuilder(hash.Length * 2);
        foreach (byte b in hash) builder.Append(b.ToString("x2"));
        return builder.ToString();
    }

    private static void LockReminder()
    {
        MessageBox.Show("订单锁保持开启。正式账户永久只读；模拟账户的策略开关本身不直接下单。", ProfileTitle, MessageBoxButtons.OK, MessageBoxIcon.Information);
        Audit("order_lock_viewed", "locked");
    }

    private static void GenerateDiagnosis()
    {
        string root = RootPath();
        string script = Path.Combine(root, "scripts", "diagnose_tray.py");
        string report = Path.Combine(root, "runtime_data", "audit", Profile, "tray_diagnostic_latest.json");
        try
        {
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = "py.exe";
            info.Arguments = "-3.12 \"" + script + "\" --profile " + Profile;
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            using (Process process = Process.Start(info)) process.WaitForExit(15000);
        }
        catch (Exception error)
        {
            MessageBox.Show("诊断脚本无法启动：" + error.Message + "\n\n报告路径：\n" + report, ProfileTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            Audit("diagnosis_error", error.GetType().Name + ": " + error.Message);
            return;
        }
        if (File.Exists(report)) Process.Start("notepad.exe", "\"" + report + "\"");
        else MessageBox.Show("诊断报告未生成：\n" + report, ProfileTitle, MessageBoxButtons.OK, MessageBoxIcon.Warning);
        Audit("diagnosis_opened", report);
    }

    private static void TryRunScheduler()
    {
        // Simulation profile owns the sole unattended v1.1.15 schedule. The
        // formal read-only profile never schedules or executes, and the master
        // strategy switch gates only the order cycle (signal/account/daily
        // record and lake sampling keep running while it is off).
        lock (scheduleLock)
        {
            if (schedulerBusy) return;
            schedulerBusy = true;
        }
        System.Threading.ThreadPool.QueueUserWorkItem(delegate
        {
            try { RunSchedulerJobs(); }
            catch { }
            finally { lock (scheduleLock) { schedulerBusy = false; } }
        });
    }

    private static void RunSchedulerJobs()
    {
        DateTime now = DateTime.Now; // local Asia/Shanghai wall clock
        string today = now.ToString("yyyy-MM-dd");
        // Read-only account facts stay fresh for both profiles; every job below
        // this line belongs to the simulation strategy schedule only.
        HourlySnapshotIfDue(now);
        BridgeDailyRecordIfDue(now, today);
        HostFactDeliveryIfDue(now);
        StrategyDeploymentIfDue(now, false);
        if (Profile != "simulation") return;
        CloseShadowIfDue(now, today);
        LakeCycleIfDue(now, today);
        DailyRecordIfDue(now, today);
        SimulationCycleIfDue(now, today);
    }

    private static void HourlySnapshotIfDue(DateTime now)
    {
        // Durable account/position facts once per hour, with a short retry after
        // a transient read-only RPC failure. This job only runs
        // scripts/run_readonly_snapshot.py: it reads the account through the
        // bridge and persists it, so broker_call_made=false and no order path is
        // touched.
        if (now < nextHourlySnapshotAttempt) return;
        string hour = now.ToString("yyyy-MM-dd HH");
        if (lastHourlySnapshotHour == hour) return;
        string configName = Profile == "simulation" ? "host_gateway.simulation.json" : "host_gateway.production_readonly.json";
        bool ok;
        string output = RunPython("run_readonly_snapshot.py", "--config config\\" + configName, 90000, out ok);
        if (output.IndexOf("\"status\": \"PASSED\"") >= 0)
        {
            lastHourlySnapshotHour = hour;
            nextHourlySnapshotAttempt = DateTime.MinValue;
            Audit("hourly_account_snapshot", "status=PASSED; orders_enabled=false; broker_call_made=false");
        }
        else
        {
            nextHourlySnapshotAttempt = now.AddMinutes(10);
            Audit("hourly_account_snapshot_blocked", output.TrimStart());
        }
    }

    private static void HostFactDeliveryIfDue(DateTime now)
    {
        // The Shadow facts endpoint is intentionally the only destination in
        // this release.  The command itself also refuses non-18666 endpoints.
        if (now < nextFactDeliveryAttempt) return;
        nextFactDeliveryAttempt = now.AddMinutes(5);
        string secret = FactSecretPath();
        if (!File.Exists(secret))
        {
            hostAgentState = "等待 Fact Secret";
            hostAgentDetail = "本机授权文件不存在";
            Audit("host_fact_delivery_blocked", "fact_secret_missing; orders_enabled=false");
            return;
        }
        string profileDirectory = Profile == "simulation" ? "simulation" : "production";
        string auditPath = Path.Combine(RootPath(), "runtime_data", "audit", Profile, "native_tray.jsonl");
        string outboxPath = Path.Combine(RootPath(), "runtime_data", "state", profileDirectory, "host_agent_outbox.sqlite3");
        string secretArg = "\"" + secret + "\"";
        string auditArg = "\"" + auditPath + "\"";
        string outboxArg = "\"" + outboxPath + "\"";
        bool collected;
        string collect = RunPython("host_agent\\collect_runtime_fact.py", "--profile " + Profile + " --host-id " + HostId() + " --audit-path " + auditArg + " --outbox-path " + outboxArg, 15000, out collected);
        if (!collected)
        {
            hostAgentState = "采集失败";
            hostAgentDetail = "本地审计事实未生成";
            Audit("host_fact_collect_blocked", collect.TrimStart());
            return;
        }
        bool delivered;
        string deliver = RunPython("host_agent\\deliver_fact_outbox.py", "--profile " + Profile + " --secret-file " + secretArg + " --outbox-path " + outboxArg + " --expected-host-id \"" + HostId() + "\" --endpoint \"" + ShadowCoordinatorEndpoint() + "\"", 20000, out delivered);
        if (deliver.IndexOf("FACT_HOST_ID_MISMATCH", StringComparison.OrdinalIgnoreCase) >= 0)
        {
            hostAgentState = "Fact Secret 不匹配";
            hostAgentDetail = "Secret host_id 与本机 host_id 不一致";
            Audit("host_fact_delivery_blocked", deliver.TrimStart());
            return;
        }
        hostAgentState = delivered ? "事实投递正常" : "事实待重试";
        hostAgentDetail = delivered ? "Outbox已确认" : "Outbox保留待补传";
        Audit(delivered ? "host_fact_delivery" : "host_fact_delivery_retry_pending", deliver.TrimStart());
    }

    private static void CloseShadowIfDue(DateTime now, string today)
    {
        if (now.Hour < 15 || (now.Hour == 15 && now.Minute < 35)) return;
        if (lastCloseShadowDate == today) return;
        if (now < nextCloseShadowAttempt) return;
        bool ok;
        string output = RunPython("run_v1_1_15_close_shadow.py", "", 180000, out ok);
        bool done = output.IndexOf("\"result\": \"RECORDED\"") >= 0 || output.IndexOf("\"result\": \"DUPLICATE\"") >= 0;
        if (done)
        {
            lastCloseShadowDate = today;
            nextCloseShadowAttempt = DateTime.MinValue;
            Audit("v1_1_15_close_shadow_auto", "done; orders_enabled=false");
        }
        else
        {
            nextCloseShadowAttempt = now.AddMinutes(10);
            Audit("v1_1_15_close_shadow_auto_blocked", output.TrimStart());
        }
    }

    private static void BridgeDailyRecordIfDue(DateTime now, string today)
    {
        // Daily durable proof of which BIGQMT_BRIDGE build is running: one
        // read-only ping (strategy liveness plus the bridge version and RPC
        // revision it answers with) together with the persisted snapshot age,
        // written under runtime_data/evidence/<profile>/bridge_daily/.  A
        // failure retries every 10 minutes so a bridge that is still coming up
        // after the close does not cost the day its evidence.
        if (now.Hour < 16 || (now.Hour == 16 && now.Minute < 30)) return;
        if (lastBridgeDailyRecordDate == today) return;
        if (now < nextBridgeDailyRecordAttempt) return;
        bool ok;
        string output = RunPython("record_bridge_daily_evidence.py", "--profile " + Profile, 60000, out ok);
        if (output.IndexOf("\"status\": \"PASSED\"") >= 0)
        {
            lastBridgeDailyRecordDate = today;
            nextBridgeDailyRecordAttempt = DateTime.MinValue;
            Audit("bridge_daily_evidence", "PASSED; strategy=BIGQMT_BRIDGE; version=" + JsonString(output, "bridge_version")
                + "; rpc_revision=" + JsonString(output, "rpc_revision")
                + "; broker_call_made=false; orders_enabled=false");
        }
        else
        {
            nextBridgeDailyRecordAttempt = now.AddMinutes(10);
            Audit("bridge_daily_evidence_blocked", output.TrimStart());
        }
    }

    private static void LakeCycleIfDue(DateTime now, string today)
    {
        if (now.Hour < 16 || (now.Hour == 16 && now.Minute < 10)) return;
        if (lastLakeCycleDate == today) return;
        if (now < nextLakeAttempt) return;
        bool ok;
        string output = RunPython("run_lake_cycle.py", "--profile " + Profile, 120000, out ok);
        bool passed = output.IndexOf("\"status\": \"PASSED\"") >= 0;
        if (passed)
        {
            lastLakeCycleDate = today;
            nextLakeAttempt = DateTime.MinValue;
            Audit("lake_cycle_auto", "PASSED");
        }
        else
        {
            nextLakeAttempt = now.AddMinutes(10);
            Audit("lake_cycle_auto_blocked", output.TrimStart());
        }
    }

    private static void DailyRecordIfDue(DateTime now, string today)
    {
        if (now.Hour < 16 || (now.Hour == 16 && now.Minute < 20)) return;
        if (lastDailyRecordDate == today) return;
        bool ok;
        string output = RunPython("record_v1_1_15_simulation_daily.py", "", 60000, out ok);
        bool passed = output.IndexOf("\"status\": \"PASSED\"") >= 0;
        if (passed)
        {
            lastDailyRecordDate = today;
            Audit("v1_1_15_daily_operations_record_auto", "PASSED");
        }
        else
        {
            Audit("v1_1_15_daily_operations_record_blocked", output.TrimStart());
        }
    }

    private static void SimulationCycleIfDue(DateTime now, string today)
    {
        // The per-strategy run switch for the v1.1.15 simulator must be on, it
        // must be a weekday, and the wall clock must be inside the A-share
        // continuous session window.
        if (!StrategyAutoRunEnabled(StrategyIdV1115)) return;
        if (now.DayOfWeek == DayOfWeek.Saturday || now.DayOfWeek == DayOfWeek.Sunday) return;
        if (now.Hour < 9 || (now.Hour == 9 && now.Minute < 35)) return;
        if (now.Hour > 14 || (now.Hour == 14 && now.Minute > 50)) return;
        if (lastExecutionCycleDate == today) return;
        if (now < nextExecutionAttempt) return;
        if (simulationCycleAttemptDate != today)
        {
            simulationCycleAttemptDate = today;
            simulationCycleAttemptsToday = 0;
        }
        if (simulationCycleAttemptsToday >= MaxSimulationCycleAttemptsPerSession)
        {
            lastExecutionCycleDate = today;
            nextExecutionAttempt = DateTime.MinValue;
            Audit("v1_1_15_cycle_auto_budget_exhausted", "attempts=" + simulationCycleAttemptsToday);
            return;
        }
        simulationCycleAttemptsToday++;
        bool ok;
        string output = RunPython("run_v1_1_15_simulation_cycle.py", "--execute", 90000, out ok);
        bool aligned = output.IndexOf("\"status\": \"ALIGNED_NO_ORDER\"") >= 0
            || output.IndexOf("\"status\": \"PREFLIGHT_PASSED_NO_ORDER\"") >= 0;
        if (aligned)
        {
            FinishSimulationCycleForToday(today, "aligned_no_order");
            return;
        }
        bool submitted = output.IndexOf("\"status\": \"SUBMITTED\"") >= 0;
        bool sellLeg = output.IndexOf("\"side\": \"SELL\"") >= 0;
        if (submitted && sellLeg)
        {
            // A v1.1.15 rotation is split on purpose: confirmation and
            // reconciliation of the sell must finish before the buy of the new
            // target is allowed. Ending the session here would leave the
            // sleeve in cash, so re-invoke inside the bounded window instead.
            nextExecutionAttempt = now.AddSeconds(60);
            Audit("v1_1_15_cycle_sell_leg_submitted", "sell leg submitted; buy leg pending reconciliation");
            return;
        }
        if (submitted)
        {
            FinishSimulationCycleForToday(today, "submitted_final_leg");
            return;
        }
        string lower = output.ToLowerInvariant();
        bool retryable = lower.IndexOf("timed out") >= 0 || lower.IndexOf("timeout") >= 0
            || lower.IndexOf("connection") >= 0 || lower.IndexOf("refused") >= 0
            || lower.IndexOf("redis") >= 0 || lower.IndexOf("rpc") >= 0
            || lower.IndexOf("duplicate") >= 0 || lower.IndexOf("admission") >= 0
            || lower.IndexOf("open orders") >= 0
            || lower.IndexOf("reconciliation") >= 0;
        if (retryable)
        {
            nextExecutionAttempt = now.AddMinutes(2);
            Audit("v1_1_15_cycle_auto_retryable", output.TrimStart());
        }
        else
        {
            // A risk/calendar/holding-period block is an intentional
            // fail-closed result: do not retry again today.
            lastExecutionCycleDate = today;
            nextExecutionAttempt = DateTime.MinValue;
            Audit("v1_1_15_cycle_auto_blocked", output.TrimStart());
        }
    }

    private static void FinishSimulationCycleForToday(string today, string reason)
    {
        lastExecutionCycleDate = today;
        nextExecutionAttempt = DateTime.MinValue;
        Audit("v1_1_15_cycle_auto", reason + "; orders_enabled=false");
    }
    private static void Audit(string eventName, string detail)
    {
        try
        {
            string directory = Path.Combine(RootPath(), "runtime_data", "audit", Profile);
            Directory.CreateDirectory(directory);
            string line = "{\"event_time\":\"" + DateTime.UtcNow.ToString("o") + "\",\"event\":\"" + JsonEscaped(eventName) + "\",\"detail\":\"" + JsonEscaped(detail) + "\",\"orders_enabled\":false,\"execution_consumer_enabled\":false}";
            File.AppendAllText(Path.Combine(directory, "native_tray.jsonl"), line + Environment.NewLine, new UTF8Encoding(false));
        }
        catch { }
    }

    private static string JsonEscaped(string value)
    {
        // A JSON string literal must not carry raw control characters: audit
        // details routinely embed multi-line tool output, and one raw newline
        // splits a single record across two physical lines, which breaks every
        // line-oriented JSONL reader. Control characters are written as JSON
        // escape sequences instead, so a record always stays on one line.
        if (value == null) return "";
        const char Quote = (char)34;
        const char Slash = (char)92;
        const char Newline = (char)10;
        const char CarriageReturn = (char)13;
        const char Tab = (char)9;
        System.Text.StringBuilder builder = new System.Text.StringBuilder(value.Length + 16);
        for (int i = 0; i < value.Length; i++)
        {
            char ch = value[i];
            if (ch == Quote || ch == Slash || ch == Newline || ch == CarriageReturn || ch == Tab || ch < (char)32)
            {
                builder.Append(Slash);
                switch (ch)
                {
                    case Quote: builder.Append(Quote); break;
                    case Slash: builder.Append(Slash); break;
                    case Newline: builder.Append('n'); break;
                    case CarriageReturn: builder.Append('r'); break;
                    case Tab: builder.Append('t'); break;
                    default: builder.Append('u').Append(((int)ch).ToString("x4")); break;
                }
            }
            else
            {
                builder.Append(ch);
            }
        }
        return builder.ToString();
    }

    private sealed class MutexHandle : IDisposable
    {
        private readonly System.Threading.Mutex inner;
        public readonly bool IsFirstInstance;
        public MutexHandle(string name) { inner = new System.Threading.Mutex(true, name, out IsFirstInstance); }
        public void Dispose() { if (IsFirstInstance) inner.ReleaseMutex(); inner.Dispose(); }
    }

    private sealed class UninstallSelectionForm : Form
    {
        private readonly ListBox list;
        private readonly Label counter;
        private readonly Label warning;
        private readonly Button ok;
        private string[] rows;
        public UninstallSelectionForm(System.Collections.Generic.IList<string> rows)
        {
            this.rows = new string[rows.Count];
            rows.CopyTo(this.rows, 0);
            Text = "选择要删除的策略（点击行=选中/取消选中，可多选）";
            FormBorderStyle = FormBorderStyle.Sizable;
            StartPosition = FormStartPosition.CenterScreen;
            MinimizeBox = false; ShowInTaskbar = false;
            ClientSize = new Size(760, 400);
            Label hint = new Label();
            hint.Text = "用鼠标点击行即可选中（高亮）或取消选中。可一次选多条。\n" +
                        "点「删除选中」删除高亮的行；什么都不想删就点「取消」。";
            hint.AutoSize = true;
            hint.Location = new Point(12, 8);
            list = new ListBox();
            list.Location = new Point(12, 56);
            list.Size = new Size(736, 280);
            list.SelectionMode = SelectionMode.MultiSimple;
            list.Font = new System.Drawing.Font("Consolas", 10F);
            foreach (string row in rows) list.Items.Add(row);
            // SelectedIndexChanged fires AFTER the selection changes (well
            // behaved in .NET Framework 4, unlike CheckedListBox.ItemCheck).
            list.SelectedIndexChanged += delegate { UpdateState(); };
            counter = new Label();
            counter.AutoSize = true;
            counter.Location = new Point(12, 344);
            counter.Text = "已选 0 / " + rows.Count + " 条";
            warning = new Label();
            warning.AutoSize = true;
            warning.Location = new Point(12, 368);
            warning.ForeColor = Color.FromArgb(170, 30, 30);
            warning.Text = "⚠ 未选中任何策略。点行选中后再点「删除选中」";
            Button all = new Button();
            all.Text = "全选";
            all.Location = new Point(12, 368);
            all.AutoSize = true;
            all.Click += delegate { for (int i = 0; i < list.Items.Count; i++) list.SetSelected(i, true); UpdateState(); };
            Button none = new Button();
            none.Text = "全不选";
            none.Location = new Point(80, 368);
            none.AutoSize = true;
            none.Click += delegate { for (int i = 0; i < list.Items.Count; i++) list.SetSelected(i, false); UpdateState(); };
            ok = new Button();
            ok.Text = "删除选中";
            ok.Location = new Point(540, 368);
            ok.AutoSize = true;
            ok.DialogResult = DialogResult.None; // no auto-close on click
            ok.Click += ConfirmClick;
            Button cancel = new Button();
            cancel.Text = "取消";
            cancel.Location = new Point(680, 368);
            cancel.AutoSize = true;
            cancel.DialogResult = DialogResult.Cancel;
            AcceptButton = ok; CancelButton = cancel;
            Controls.Add(hint); Controls.Add(list); Controls.Add(counter); Controls.Add(warning); Controls.Add(all); Controls.Add(none); Controls.Add(ok); Controls.Add(cancel);
            UpdateState();
        }

        private void UpdateState()
        {
            int count = list.SelectedIndices.Count;
            counter.Text = "已选 " + count + " / " + list.Items.Count + " 条";
            warning.Text = count == 0 ? "⚠ 未选中任何策略。点行选中后再点「删除选中」" : "";
            ok.Enabled = count > 0;
        }

        private void ConfirmClick(object sender, EventArgs e)
        {
            if (list.SelectedIndices.Count == 0)
            {
                UpdateState();
                return;
            }
            DialogResult = DialogResult.OK;
            Close();
        }

        public int[] SelectedIndicesCopy()
        {
            int[] copy = new int[list.SelectedIndices.Count];
            list.SelectedIndices.CopyTo(copy, 0);
            return copy;
        }
    }

    private sealed class PasswordPromptForm : Form
    {
        private readonly TextBox input;
        public PasswordPromptForm(string title, string label)
        {
            Text = title;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            StartPosition = FormStartPosition.CenterScreen;
            MaximizeBox = false; MinimizeBox = false; ShowInTaskbar = false;
            ClientSize = new Size(360, 110);
            Label prompt = new Label();
            prompt.Text = label;
            prompt.AutoSize = true;
            prompt.Location = new Point(12, 12);
            input = new TextBox();
            input.Location = new Point(12, 40);
            input.Width = 336;
            input.UseSystemPasswordChar = true;
            Button ok = new Button();
            ok.Text = "确定";
            ok.Location = new Point(212, 72);
            ok.DialogResult = DialogResult.OK;
            Button cancel = new Button();
            cancel.Text = "取消";
            cancel.Location = new Point(286, 72);
            cancel.DialogResult = DialogResult.Cancel;
            AcceptButton = ok; CancelButton = cancel;
            Controls.Add(prompt); Controls.Add(input); Controls.Add(ok); Controls.Add(cancel);
        }
        public bool EnteredPassword(out string password)
        {
            password = input.Text ?? "";
            return password.Length > 0;
        }
    }
}
